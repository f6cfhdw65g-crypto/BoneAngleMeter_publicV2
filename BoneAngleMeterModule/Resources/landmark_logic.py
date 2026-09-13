import numpy as np
import os.path as osp
import slicer

class SimpleLandmark:
    def __init__(self, name, description="", image_path=""):
        self.name = name
        self.placed = False
        self.change_callbacks = []
        self.description = description
        self.image_path = image_path

        # Internal members
        self._markups_node = None
        self._id = None
        self._private_observers = []

    def set_markups_node_id(self, id):
        self._markups_node = slicer.mrmlScene.GetNodeByID(id)

        # Set automatic glyph style
        self._markups_node.GetDisplayNode().SetGlyphType(self._markups_node.GetDisplayNode().ThickCross2D)
        self._markups_node.GetDisplayNode().SetGlyphScale(2.5)

    def add_change_callback(self, callback):
        self.change_callbacks.append(callback)

    def show(self):
        if self._id is not None:
            self._markups_node.SetNthControlPointVisibility(self._id, True)

    def hide(self):
        self.stop_interaction()
        if self._id is not None:
            self._markups_node.SetNthControlPointVisibility(self._id, False)

    def start_interaction(self):
        if self.placed:
            self._markups_node.SetNthControlPointLocked(self._id, False)
            self._markups_node.SetNthControlPointSelected(self._id, True)
            self.center_in_slices()
            self._private_observers.append(self._markups_node.AddObserver(slicer.vtkMRMLMarkupsNode.PointModifiedEvent, 
                                                                         lambda caller, event: self._changed_callback(caller)))
        else:
            slicer.modules.markups.logic().StartPlaceMode(0)
            self._private_observers.append(self._markups_node.AddObserver(slicer.vtkMRMLMarkupsNode.PointAddedEvent, 
                                                                         lambda caller, event: self._added_callback()))
            self._private_observers.append(self._markups_node.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, 
                                                                         lambda caller, event: self._defined_callback()))

    def stop_interaction(self):
        if self.placed:
            self._markups_node.SetNthControlPointLocked(self._id, True)
            self._markups_node.SetNthControlPointSelected(self._id, False)
        
        # Turn off placement mode and remove observers
        for observer in self._private_observers:
            self._markups_node.RemoveObserver(observer)

        interaction_node = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
        interaction_node.SwitchToViewTransformMode()
        interaction_node.SetPlaceModePersistence(0)                                                       

    def center_in_slices(self, excluded_slice_nodes=None):
        position_RAS = [0.0, 0.0, 0.0]
        self._markups_node.GetNthControlPointPosition(self._id, position_RAS)

        if excluded_slice_nodes is None:
            slicer.vtkMRMLSliceNode.JumpAllSlices(slicer.mrmlScene, *position_RAS, slicer.vtkMRMLSliceNode.CenteredJumpSlice)
        else:
            slice_nodes = slicer.util.getNodesByClass("vtkMRMLSliceNode")
            for slice_node in slice_nodes:
                if slice_node.GetName() not in excluded_slice_nodes:
                    slice_node.SetJumpModeToCentered()
                    slice_node.JumpSlice(*position_RAS)

    def define(self, x, y, z):
        self._markups_node.AddControlPoint([x, y, z], self.name)
        self._id = self._markups_node.GetNumberOfControlPoints() - 1
        self.placed = True
        self._changed_callback()

    def delete(self):
        '''
        Un-places this landmark so it can be placed again. Note: all landmarks on a side share
        one markups node, and this landmark's _id is a raw index into it, so the underlying
        fiducial point is hidden and locked rather than physically removed from the node -
        removing it would silently shift the _id of every other already-placed landmark with a
        higher index, corrupting their positions.
        '''
        if self.placed and self._id is not None:
            self.stop_interaction()
            self._markups_node.SetNthControlPointVisibility(self._id, False)
            self._markups_node.SetNthControlPointLocked(self._id, True)
            self._id = None
            self.placed = False
            for cb in self.change_callbacks:
                cb()

    def get_position(self):
        if self._id is None or not self.placed:
            return None
        xyz_buffer = [0.0, 0.0, 0.0]
        self._markups_node.GetNthControlPointPosition(self._id, xyz_buffer)
        return np.array(xyz_buffer)

    def _added_callback(self):
        '''
        Called when a point is added (but not necessarily placed). Takes care of giving the right label to the newly added point
        '''
        id = self._markups_node.GetNumberOfControlPoints() - 1 # id is only temporary until the point is defined
        self._markups_node.SetNthControlPointLabel(id, self.name)
        
    def _defined_callback(self):
        '''
        Called when a point is placed/defined. 
        '''
        self._id = self._markups_node.GetNumberOfControlPoints()-1
        self.placed = True
        self.stop_interaction()
        self._changed_callback()
        self.start_interaction()

    def _changed_callback(self, caller=None):
        '''
        Called when a point is changed (including defined). Triggers updates to all dependent measurements
        '''
        if caller is not None:
            calling_node = caller.GetAttribute("Markups.MovingInSliceView")
        else:
            calling_node = None
        self.center_in_slices([calling_node])

        for cb in self.change_callbacks:
            cb()


class SphereLandmark(SimpleLandmark):
    '''
    A landmark placed at a sphere's center, with a radius the user adjusts by hand (e.g. via a
    spinbox in the GUI) rather than one computed from several points. Used where visually
    matching a sphere against the bone surface is more practical than an automatic best-fit,
    for example locating a femoral condyle.
    '''
    def __init__(self, name, description="", image_path="", default_radius=8.0):
        super().__init__(name, description, image_path)
        self.radius = default_radius

    def set_radius(self, radius):
        self.radius = radius
        for cb in self.change_callbacks:
            cb()

    def get_sphere(self):
        if not self.placed:
            return None
        return self.get_position(), self.radius

