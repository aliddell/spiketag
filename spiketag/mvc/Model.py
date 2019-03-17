import numpy as np
from sklearn.neighbors import KDTree
from ..base.SPK import _construct_transformer
from ..base import *
from ..utils.conf import info 
from ..utils import conf
from ..utils.utils import Timer
from ..analysis.place_field import place_field


class MainModel(object):
    """
    filename is the mua binary file
    spktag_filename is the spiketag file, if None, Model will do clustering
    other parameters are metadata of the binary file

    Model contains four sub-objects:
       -- mua: MUA; mua.tospk
       -> spk: SPK; spk.tofet
       -> fet: FET; fet.toclu, fet.get
       -> clu: dict, every item is a CLU on that channel; clu.merge, clu.split, clu.move  etc..
    """

    def __init__(self, mua_filename, spk_filename, probe=None, spktag_filename=None, 
                 numbytes=4, binary_radix=13, scale=True, spklen=19, corr_cutoff=0.9, cutoff=[-15000, 1000],
                 fet_method='pca', fetlen=6, fet_whiten=False,
                 clu_method='hdbscan', fall_off_size=18, n_jobs=24,
                 time_segs=None,
                 playground_log=None, session_id=0, 
                 pc=None, bin_size=4, v_cutoff=5, behavior_start_time=0.,
                 sort_movment_only=False):

        # raw recording param
        self.mua_filename = mua_filename
        self.spk_filename = spk_filename
        self.spktag_filename = spktag_filename
        self.probe = probe
        self.numbytes = numbytes
        self.binpoint = binary_radix
        self.scale = scale

        # mua param
        self._corr_cutoff = corr_cutoff
        self._spklen = spklen 
        self._cutoff = cutoff
        self._time_segs = time_segs

        # fet param
        self.fet_method = fet_method
        self._fet_whiten = fet_whiten
        self._fetlen = fetlen

        # clu param
        self.clu_method = clu_method
        self._fall_off_size = fall_off_size
        self._n_jobs = n_jobs

        # playground log
        self.time_still = None
        # TODO1: fix this
        if playground_log is not None:
            self.pc = place_field(logfile=playground_log, session_id=session_id, v_cutoff=v_cutoff)
            self.pc.ts += behavior_start_time
            self.ts, self.pos = self.pc.ts, self.pc.pos
            self.v_smoothed, self.v = self.pc.v_smoothed, self.pc.v
            self.v_still_idx = self.pc.v_still_idx
            if sort_movment_only:
                self.time_still = self.ts[self.v_still_idx] 

        # TODO2: test this
        elif pc is not None:
            self.pc = pc
            self.pc.ts += behavior_start_time  # behavior start time relative to the time 0 of ephys
            self.pc.initialize(bin_size=bin_size, v_cutoff=v_cutoff)
            if sort_movment_only:
                self.time_still = self.pc.ts[self.pc.v_still_idx]

        else:
            self.pc = None

        self._model_init_(self.spktag_filename)



    def _model_init_(self, spktag_filename=None):
        '''
        If spktag_filename is given, Model will generate spk,fet,clu from
        loading spktag array, rather than compute it from mua. 
        Otherwise, it would assume that there is no stored infomation and 
        everything needs to be calculated from mua
        '''
         # The first time
        if spktag_filename is None:

            info('load mua data')
            self.mua = MUA(probe        = self.probe,
                           mua_filename = self.mua_filename, 
                           spk_filename = self.spk_filename, 
                           numbytes     = self.numbytes, 
                           binary_radix = self.binpoint,
                           scale        = self.scale,
                           cutoff       = self._cutoff,         # for amp   cut_off
                           time_segs    = self._time_segs,      # for time  cut_off
                           time_still   = self.time_still,      # for speed cut_off
                           lfp          = False)

            self.get_spk(amp_cutoff=False)
            self.get_fet()

        # After first time
        else:
            self.spktag = SPKTAG(probe=self.probe)
            info('load spktag file')
            self.spktag.fromfile(spktag_filename)
            self.gtimes = self.spktag.to_gtimes()
            self.spk = self.spktag.tospk()
            self.fet = self.spktag.tofet()
            self.clu = self.spktag.toclu()

            info('load mua data for wave view')
            self.mua = MUA(probe        = self.probe,
                           mua_filename = self.mua_filename, 
                           spk_filename = self.spk_filename, 
                           numbytes     = self.numbytes, 
                           binary_radix = self.binpoint,
                           scale        = self.scale,
                           cutoff       = self._cutoff, 
                           time_segs    = self._time_segs, 
                           time_still   = self.time_still,
                           lfp          = False)
            self.mua.spk_times = self.gtimes
            self.spk_times = self.mua.spk_times
            info('Model.spktag is generated, nspk:{}'.format(self.spktag.nspk))

        self.groups = self.probe.grp_dict.keys()
        self.ngrp   = len(self.groups)


    def get_spk(self, amp_cutoff=True, speed_cutoff=True, time_cutoff=True):
        info('extract spikes from pivital meta data')
        self.spk = self.mua.tospk(amp_cutoff=amp_cutoff,
                                  speed_cutoff=speed_cutoff,
                                  time_cutoff=time_cutoff)

        info('grouping spike time')
        self.gtimes = self.mua.spk_times


    def get_fet(self):
        info('extract features with {}'.format(self.fet_method))
        self.fet = self.spk.tofet(method=self.fet_method, 
                                  whiten=self._fet_whiten,
                                  ncomp=self._fetlen)
        # all clu are zeroes when fets are initialized
        self.clu = self.fet.clu

        self.clu_manager = status_manager()
        for _clu in self.clu.values():
            self.clu_manager.append(_clu)


    def sort(self, clu_method, group_id='all', **kwargs):
        # info('removing high corr noise from spikes pool')
        # self.mua.remove_high_corr_noise(corr_cutoff=self._corr_cutoff)

        # info('removing all spks on group which len(spks) less then fetlen')
        # self.mua.remove_groups_under_fetlen(self._fetlen)

        info('clustering with {}'.format(clu_method))
        self.fet.toclu(method=clu_method, group_id=group_id, **kwargs)

        self.spktag = SPKTAG(self.probe,
                             self.spk, 
                             self.fet, 
                             self.clu,
                             self.gtimes)
        info('Model.spktag is generated, nspk:{}'.format(self.spktag.nspk))


    def cluster(self, group_id, method, **params):
        self.sort(clu_method=method, group_id=group_id, **params)


    def construct_transformer(self, group_id, ndim=4):
        '''
        construct transformer parameters for a specific group
        y = a(xP+b)
        P: _pca_comp
        b: _shift
        a: _scale
        '''
        # concateated spike waveforms from one channel group
        r = self.spk[group_id]
        x = r.transpose(0,2,1).ravel().reshape(-1, r.shape[1]*r.shape[2])
        # construct transfomer params
        _pca_comp, _shift, _scale = _construct_transformer(x, ncomp=ndim)
        return _pca_comp, _shift, _scale


    def construct_kdtree(self, group_id, global_ids=None, n_dim=4):
        self.kd = {} 
        for clu_id, value in self.clu[group_id].index.items():
            diff_ids = np.setdiff1d(value, global_ids, assume_unique=True)
            if len(diff_ids) > 0:
                fet = self.fet[group_id][diff_ids][:, :n_dim]
                self.kd[KDTree(fet)] = clu_id


    def predict(self, group_id, global_ids, method='knn', k=10, n_dim=4):
        X = self.fet[group_id][global_ids][:,:n_dim]
        if X.ndim==1: X=X.reshape(1,-1)

        if method == 'knn':
            self.construct_kdtree(group_id, global_ids)
            d = []
            for _kd in self.kd.iterkeys():
                tmp = _kd.query(X, k)[0]
                d.append(tmp.mean(axis=1))
            d = np.vstack(np.asarray(d))
            labels = np.asarray(self.kd.values())[np.argmin(d, axis=0)]
        return labels


    def tofile(self, filename=None):
        '''
        This should automatically update the spktag array and save
        So that next time it can be loaded and avoid re-clustering
        '''
        if filename is not None:
            self.spktag.tofile(filename)
        elif self.spktag_filename is not None:
            self.spktag.tofile(self.spktag_filename)
        else:
            barename = self.filename.split('.')[0]
            self.spktag_filename = barename + '_spktag.bin'
            self.spktag.tofile(self.spktag_filename)

    def refine(self, group, global_ids):
        info("received model modified event, refine spikes[group={}, global_ids={}]".format(group, global_ids))
        labels = self.predict(group, global_ids) 
        info("the result of refine: {}".format(labels))
        self.clu[group].refill(global_ids, labels)
    
    def remove_spk(self, group, global_ids):
        '''
        Delete spks using global_ids, spks includes SPK, FET, CLU, SPKTAG. 
        '''
        info("received model modified event, removed spikes[group={}, global_ids={}]".format(group, global_ids))
        with Timer("[MODEL] Model -- remove spk from times", verbose=conf.ENABLE_PROFILER):
            self.gtimes[group] = np.delete(self.gtimes[group], global_ids)
        with Timer("[MODEL] Model -- remove spk from SPK.", verbose=conf.ENABLE_PROFILER):
            self.spk.remove(group, global_ids)
        with Timer("[MODEL] Model -- SPK to FET.", verbose=conf.ENABLE_PROFILER):
            self.fet[group] = self.spk._tofet(group, method=self.fet_method)
        with Timer("[MODEL] Model -- FET to CLU.", verbose=conf.ENABLE_PROFILER):
            self.clu[group] = self.fet._toclu(group)
            
    def mask_spk(self, group, global_ids):
        '''
        Mask spks using global_ids, spks includes SPK, FET, CLU, SPKTAG. 
        '''
        info("received model modified event, mask spikes[group={}, global_ids={}]".format(group, global_ids))
        
        with Timer("[MODEL] Model -- mask spk from SPK.", verbose=conf.ENABLE_PROFILER):
            self.spk.mask(group, global_ids)
        with Timer("[MODEL] Model -- SPK to FET.", verbose=conf.ENABLE_PROFILER):
            self.fet[group] = self.spk._tofet(group, method=self.fet_method)
        with Timer("[MODEL] Model -- FET to CLU", verbose=conf.ENABLE_PROFILER):
            self.clu[group] = self.fet._toclu(group)

