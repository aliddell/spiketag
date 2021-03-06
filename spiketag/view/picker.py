from vispy import scene, app
import numpy as np
from matplotlib import path

#------------------------------------------------------------------------------
# Picker
#------------------------------------------------------------------------------
class Picker(object):

    """Class that pick the markers by lasso or rectangle.



    Parameters
    ----------
    cur_scene :  scene
        the current scene of canvas.
    cur_view  :  view
        the current view of scene, consider this as local coordinate
    cur_scatter: Markers
        the be selected markers

    Example
    -------

    ```
       picker = Picker(self.scene,self.view,markers)
       picker.origin_point(point)
       picker.cast_net(cur_position,ptype='lasso')
       selected = picker.pick(beSelectedPoints)
    ```

    """

    def __init__(self,cur_scene,mapping):
        """
           origin: save origin because when we draw rectangle, we need to use origin to calculate the width and height
           vertices, line: vertices is point position which be used to draw a line
           mapping: the mapping from markers coordinate to view coordinate
        """
        self._origin = (0, 0)
        self._vertices = []
        self._line = None
        self._mapping = mapping 
        self._scene = cur_scene
        self._trigger = False

    """
        save the origin point when draw begin.

        Parameters
        ----------
        point :  array
            2d, screen coordinate,usually the point is the first press of mouse.
    """
    def origin_point(self,point):
        self.reset()

        self._origin = point
        self._line = scene.visuals.Line(color='white', method='gl',
                                       parent=self._scene)
        self._trigger = True

    """
        cast a net by rectange or lasso, rectange is default

        Parameters
        ----------
        pos :    array
            2d, screen coordinate,usually the point when mouse moving.
        ptype :  string
            type of cast, rectangle or lasso
    """
    def cast_net(self,pos,ptype='rectangle'):
        if not self._trigger:
            return 
        
        if ptype == 'rectangle':
            self._cast_rectangle(pos)
        elif ptype == 'lasso':
            self._cast_lasso(pos)
        else:
            raise RuntimeError('not support yet!')


    """
        pick points from given samples because the mapping from marker coordinate to screen coordinate which given before,
        return indices of points be selected

        Parameters
        ----------
        samples :    array
            samples which be selected
        ptype :      string
            type of cast, rectangle or lasso
        return:      array
            points be selected
    """
    def pick(self, samples, auto_disappear=True):
        if not self._trigger:
            return np.array([])

        mask = np.array([])
        if len(self._vertices):
            data = self._mapping.map(samples[:, :3])[:, :2]
            select_path = path.Path(self._vertices, closed=True)
            selected = select_path.contains_points(data)
            mask = np.where(selected)[0]
        if auto_disappear:
            self.reset()
        return mask

    """
        clear all values
    """
    def reset(self):
        self._vertices = []
        if self._line:
            self._line.parent = None
            self._line = None
        self._origin = None
        self._trigger = False



    """
        cast by rectangle, basically get the vertices which can draw the rectangle
    """
    def _cast_rectangle(self,pos):
        width = pos[0] - self._origin[0]
        height = pos[1] - self._origin[1]
        if width and height:
            center = (width/2. + self._origin[0],
                      height/2.+self._origin[1], 0)
            self._vertices = self._gen_rectangle_vertice(center, abs(height), abs(width))
            self._line.set_data(np.array(self._vertices))

    """
        cast by lasso, need all position when mouse moving
    """
    def _cast_lasso(self,pos):
        self._vertices.append(pos)
        self._line.set_data(np.array(self._vertices))


    """
        use the scene.visuals.Rectangle to get the vertices.
    """
    def _gen_rectangle_vertice(self,center, height, width):
        # TODO: here is little wired, but becuase the function generate_vertices of Rectangle.py doesn't update the
        #       value of height and width, why they doesnt do this, so wired
        rectangle = scene.visuals.Rectangle(height=height,width=width)
        radius = np.array([.0,.0,.0,.0])
        return rectangle._generate_vertices(center=center,radius=radius,height=height,width=width)[1:, ..., :2]

