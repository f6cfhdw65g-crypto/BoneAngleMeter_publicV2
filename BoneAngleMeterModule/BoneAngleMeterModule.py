import qt, ctk, vtk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import errorDisplay

import os.path as osp
import csv
import numpy as np
from copy import deepcopy
import locale
locale.setlocale(locale.LC_ALL, '')

from Resources.measurements import MEASUREMENTS
from Resources.landmarks import LANDMARKS

MODULE_PATH = osp.dirname(__file__)
#
# BoneAngleMeterModule
#

class BoneAngleMeterModule(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Bone Angle Meter"
    self.parent.categories = ["Measurements"]
    self.parent.dependencies = []
    self.parent.contributors = ["Juliette Burg"]
    self.parent.helpText = """
This is a module for measuring bone angles based on landmarks.
"""
    self.parent.helpText += self.getDefaultModuleDocumentationLink()
    self.parent.acknowledgementText = """
Developed during Juliette's doctorate at CTK, LMU Munich.
"""


class BoneAngleMeterModuleWidget(ScriptedLoadableModuleWidget):
    """
    Base widget that manages the measurement groups
    """

    SEGMENTATION_NODE_NAME = "Automatic Bone Segmentation Node"

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        #####################
        # GUI and connections
        #####################
        # Automatic Segmentation
        segmentation_collapsible_button = ctk.ctkCollapsibleButton()
        segmentation_collapsible_button.text = "3D Segmentation"
        self.layout.addWidget(segmentation_collapsible_button)
        segmentation_form_layout = qt.QFormLayout(segmentation_collapsible_button)
        self.apply_segmentation_button = qt.QPushButton("Apply")
        self.apply_segmentation_button.connect('clicked(bool)', self.onApplySegmentation)
        segmentation_form_layout.addRow("Segmentation", self.apply_segmentation_button)

        self.threshold_lower = qt.QSpinBox()
        self.threshold_lower.setRange(-3000, 3000)
        self.threshold_lower.setValue(300)
        self.threshold_upper = qt.QSpinBox()
        self.threshold_upper.setRange(-3000, 3000)
        self.threshold_upper.setValue(3000)
        segmentation_form_layout.addRow("Lower threshold", self.threshold_lower)
        segmentation_form_layout.addRow("Upper threshold", self.threshold_upper)

        self.smoothing = qt.QDoubleSpinBox()
        self.smoothing.setRange(0, 1)
        self.smoothing.setDecimals(1)
        self.smoothing.setSingleStep(0.1)
        self.smoothing.setValue(0.5)
        segmentation_form_layout.addRow("Surface smoothing", self.smoothing)

        self.opacity_slider = qt.QSlider(qt.Qt.Horizontal)
        self.opacity_slider.setMinimum(0)
        self.opacity_slider.setMaximum(100)
        self.opacity_slider.setValue(70)
        self.opacity_slider.setToolTip(
            "3D opacity of the bone surface. Lower it to see landmarks placed inside the bone (e.g. femur head, condyle centers).")
        self.opacity_slider.valueChanged.connect(self.onOpacityChanged)
        segmentation_form_layout.addRow("3D Opacity", self.opacity_slider)

        self.segmentation_status = qt.QLabel("no segmentation")
        segmentation_form_layout.addRow("Status", self.segmentation_status)     

        # Measurements panel, embedded directly in this module's sidebar (always visible next to
        # the 3D/slice views) instead of a separate window - no switching between windows needed.
        # Wrapped in a collapsible section (like "3D Segmentation" above) so the whole thing can
        # be shown/hidden as one unit.
        measurements_collapsible_button = ctk.ctkCollapsibleButton()
        measurements_collapsible_button.text = "Measurements"
        self.layout.addWidget(measurements_collapsible_button)
        measurements_layout = qt.QVBoxLayout(measurements_collapsible_button)

        self.side_selector = qt.QComboBox()
        self.side_selector.addItems(["Left", "Right"])
        self.side_selector.currentIndexChanged.connect(self._on_side_changed)

        self.left_panel = MeasurementsPanel('left',
            slicer.modules.markups.logic().AddNewFiducialNode("BoneAngleMeterFiducialsLeft"), self)
        self.right_panel = MeasurementsPanel('right',
            slicer.modules.markups.logic().AddNewFiducialNode("BoneAngleMeterFiducialsRight"), self)

        self.side_stack = qt.QStackedWidget()
        self.side_stack.addWidget(self.left_panel)
        self.side_stack.addWidget(self.right_panel)

        side_row = qt.QHBoxLayout()
        side_row.addWidget(qt.QLabel("Side"))
        side_row.addWidget(self.side_selector)
        side_row.addStretch(1)
        side_row_widget = qt.QWidget()
        side_row_widget.setLayout(side_row)

        measurements_layout.addWidget(side_row_widget)
        measurements_layout.addWidget(self.side_stack, 1)

    def cleanup(self):
        pass

    def enter(self):
        # Called by Slicer whenever the user switches to this module's tab. Also call the base
        # class's own enter(), if it defines one, in case Slicer's module-switching machinery
        # relies on it.
        if hasattr(ScriptedLoadableModuleWidget, "enter"):
            ScriptedLoadableModuleWidget.enter(self)
        self._current_panel().activate()

    def exit(self):
        # Called by Slicer whenever the user switches away to another module's tab.
        if hasattr(ScriptedLoadableModuleWidget, "exit"):
            ScriptedLoadableModuleWidget.exit(self)
        self._current_panel().deactivate()

    def _current_panel(self):
        return self.side_stack.currentWidget()

    def _on_side_changed(self, index):
        old_panel = self.right_panel if index == 1 else self.left_panel
        old_panel.deactivate()
        self.side_stack.setCurrentIndex(index)
        self._current_panel().activate()

    def _apply_opacity(self, segmentation_node, opacity=None):
        display_node = segmentation_node.GetDisplayNode()
        if display_node is None:
            return
        if opacity is None:
            opacity = self.opacity_slider.value / 100.0
        # SetOpacity3D is the segmentation-specific API for 3D surface opacity; fall back to the
        # generic display node opacity if it's ever unavailable.
        if hasattr(display_node, "SetOpacity3D"):
            display_node.SetOpacity3D(opacity)
        else:
            display_node.SetOpacity(opacity)

    def onOpacityChanged(self, value):
        opacity = value / 100.0
        # Apply to every segmentation currently in the scene, not just the one this module
        # creates, so segmentations built separately (e.g. in Segment Editor) are covered too.
        for segmentation_node in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
            self._apply_opacity(segmentation_node, opacity)

    def onApplySegmentation(self):
        self.segmentation_status.setText("working...")

        # Get volume data
        volume_nodes = slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")
        if len(volume_nodes) == 0:
            self.segmentation_status.setText("No data found")
            return
        if len(volume_nodes) > 1:
            self.segmentation_status.setText("Multiple volumes found. Only one volume is supported currently.")
            return
        volume_node = volume_nodes[0]

        # Create segmentation
        segmentation_node = slicer.mrmlScene.GetFirstNodeByName(self.SEGMENTATION_NODE_NAME)
        if segmentation_node is not None:
            slicer.mrmlScene.RemoveNode(segmentation_node)
        segmentation_node = slicer.mrmlScene.AddNewNodeByClassWithID("vtkMRMLSegmentationNode", "", self.SEGMENTATION_NODE_NAME)
        segmentation_node.CreateDefaultDisplayNodes() # only needed for display
        segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)
        segmentation_node.SetName(self.SEGMENTATION_NODE_NAME)
        segment_id = segmentation_node.GetSegmentation().AddEmptySegment("Bones")

        # Create segment editor to get access to effects
        segment_editor_widget = slicer.qMRMLSegmentEditorWidget()
        segment_editor_widget.setMRMLScene(slicer.mrmlScene)
        segment_editor_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
        segment_editor_widget.setMRMLSegmentEditorNode(segment_editor_node)
        segment_editor_widget.setSegmentationNode(segmentation_node)
        segment_editor_widget.setCurrentSegmentID(segment_id)
        segment_editor_widget.setMasterVolumeNode(volume_node)

        # Thresholding
        segment_editor_widget.setActiveEffectByName("Threshold")
        effect = segment_editor_widget.activeEffect()
        effect.setParameter("MinimumThreshold", f"{self.threshold_lower.value}")
        effect.setParameter("MaximumThreshold", f"{self.threshold_upper.value}")
        effect.self().onApply()

        # Clean up
        segment_editor_widget = None
        slicer.mrmlScene.RemoveNode(segment_editor_node)

        # Smoothing
        segmentation_node.GetSegmentation().SetConversionParameter("Smoothing factor",f"{self.smoothing.value}")

        # Make segmentation results visible in 3D
        segmentation_node.CreateClosedSurfaceRepresentation()

        # Center the 3d View on the scene
        layout_manager = slicer.app.layoutManager()
        three_d_Widget = layout_manager.threeDWidget(0)
        three_d_view = three_d_Widget.threeDView()
        three_d_view.resetFocalPoint()

        # Make segmentation invisible in sliced and set colors
        segmentation_node.GetDisplayNode().SetAllSegmentsVisibility2DOutline(False)
        segmentation_node.GetDisplayNode().SetAllSegmentsVisibility2DFill(False)
        segmentation_node.GetSegmentation().GetSegment(segment_id).SetColor(241/255, 241/255, 145/255)
        self.onOpacityChanged(self.opacity_slider.value)

        self.segmentation_status.setText("ok")

class MeasurementsPanel(qt.QWidget):
    '''
    Panel containing one side's measurement UI (landmark stack of measurements). Embedded
    directly in the module's own sidebar via a side selector + stacked widget, so the whole
    module lives in a single page next to the 3D/slice views with no separate window at all.
    '''
    def __init__(self, side, markup_node_id, base_widget):
        super().__init__()

        self.markup_node_id = markup_node_id
        self.base_widget = base_widget

        if side.lower() == 'left':
            self.side = 'left'
        elif side.lower() == 'right':
            self.side = 'right'
        else:
            raise ValueError(f"side should be eigher 'left' or 'right'. Found '{side}'.")

        self.import_landmarks_button = qt.QPushButton("Import")
        self.import_landmarks_button.setToolTip(f"Import {self.side} landmarks from a CSV file.")
        self.import_landmarks_button.clicked.connect(self._import_landmarks)
        self.import_landmarks_button.setDefault(False)
        self.import_landmarks_button.setAutoDefault(False)
        self.export_landmarks_button = qt.QPushButton("Export")
        self.export_landmarks_button.setToolTip(f"Export {self.side} landmarks to a CSV file.")
        self.export_landmarks_button.clicked.connect(self._export_landmarks)
        self.export_landmarks_button.setDefault(False)
        self.export_landmarks_button.setAutoDefault(False)
        self.export_measurements_button = qt.QPushButton("Export Results")
        self.export_measurements_button.setToolTip(f"Export {self.side} measurement results to a CSV file.")
        self.export_measurements_button.clicked.connect(self._export_measurements)
        self.export_measurements_button.setDefault(False)
        self.export_measurements_button.setAutoDefault(False)

        self.measurement_list = qt.QListWidget(self)
        self.measurement_stack = qt.QStackedWidget(self)
        self.measurement_list.currentRowChanged.connect(self._change_row)

        # Model nodes for visualizing fitted spheres (femur head / condyle centers), keyed by
        # sphere label (e.g. "femur head"). Created lazily the first time they're needed.
        self.sphere_nodes = {}
        self.spheres_visible = True

        # Model nodes for visualizing the axis lines compared in each measurement, keyed by
        # axis label (e.g. "Femoral shaft axis"). Colors are assigned by position (1st axis /
        # 2nd axis) from AXIS_PALETTE, consistently across every measurement.
        self.axis_nodes = {}
        self.axes_visible = True
        self.AXIS_PALETTE = [(0.15, 0.85, 0.95), (0.95, 0.35, 0.85), (0.95, 0.65, 0.15), (0.55, 0.85, 0.25)]

        self.show_spheres_checkbox = qt.QCheckBox("Show fitted spheres")
        self.show_spheres_checkbox.setChecked(True)
        self.show_spheres_checkbox.setToolTip(
            "Show/hide the translucent spheres fitted to the femur head and condyles in the 3D view.")
        self.show_spheres_checkbox.toggled.connect(self._on_show_spheres_toggled)

        self.show_axes_checkbox = qt.QCheckBox("Show axis lines")
        self.show_axes_checkbox.setChecked(True)
        self.show_axes_checkbox.setToolTip(
            "Show/hide the colored lines for the two axes compared by the current measurement.")
        self.show_axes_checkbox.toggled.connect(self._on_show_axes_toggled)

        self.show_labels_checkbox = qt.QCheckBox("Show landmark labels")
        self.show_labels_checkbox.setChecked(True)
        self.show_labels_checkbox.setToolTip("Show/hide the text labels next to each landmark point in the 3D view.")
        self.show_labels_checkbox.toggled.connect(self._on_show_labels_toggled)

        self.delete_all_button = qt.QPushButton("Delete All")
        self.delete_all_button.setToolTip(f"Removes every placed {self.side} landmark so they can be re-placed from scratch.")
        self.delete_all_button.clicked.connect(self._delete_all_landmarks)
        self.delete_all_button.setDefault(False)
        self.delete_all_button.setAutoDefault(False)

        # Create deep-copy of all landmarks for this side
        self.landmarks = deepcopy(LANDMARKS)
        for landmark in self.landmarks:
            landmark.set_markups_node_id(self.markup_node_id)

        # Create all measurements
        for measurement in MEASUREMENTS:
            m = measurement()
            m.set_side(self.side)
            m.register_landmarks(self.landmarks)
            self.measurement_stack.addWidget(MeasurementWidget(m, self))
            self.measurement_list.addItem(m.name)
        
        self.measurement_list.setMaximumHeight(140)

        checkboxes_row = qt.QHBoxLayout()
        checkboxes_row.addWidget(self.show_spheres_checkbox)
        checkboxes_row.addWidget(self.show_axes_checkbox)
        checkboxes_row.addWidget(self.show_labels_checkbox)
        checkboxes_row_widget = qt.QWidget()
        checkboxes_row_widget.setLayout(checkboxes_row)

        controls_layout = qt.QVBoxLayout()
        controls_layout.addWidget(self.measurement_list)
        controls_layout.addWidget(checkboxes_row_widget)
        controls_widget = qt.QWidget()
        controls_widget.setLayout(controls_layout)

        # Small, grouped action buttons at the very end of the panel, below the measurement content
        action_row = qt.QHBoxLayout()
        for button in [self.delete_all_button, self.import_landmarks_button,
                       self.export_landmarks_button, self.export_measurements_button]:
            button.setMaximumHeight(24)
            action_row.addWidget(button)
        action_row_widget = qt.QWidget()
        action_row_widget.setLayout(action_row)

        layout = qt.QVBoxLayout()
        layout.addWidget(controls_widget)
        layout.addWidget(self.measurement_stack, 1)
        layout.addWidget(action_row_widget)

        self.setLayout(layout)

    def _export_landmarks(self):
        file_name = qt.QFileDialog.getSaveFileName(self, 'Export landmarks', '',"CSV File (*.csv)")
        if file_name == "": 
            return
        with open(file_name, 'w+', newline='') as csvfile:
            fieldnames = ['landmark name', 'x', 'y', 'z', 'radius']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';' 
                                    if locale.localeconv()['decimal_point'] == "," else ",", quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            for landmark in self.landmarks:
                if landmark.placed:
                    position = landmark.get_position()
                    radius = getattr(landmark, "radius", None)
                    writer.writerow({"landmark name": landmark.name, 
                                     "x": locale.str(position[0]), 
                                     "y": locale.str(position[1]), 
                                     "z": locale.str(position[2]),
                                     "radius": locale.str(radius) if radius is not None else ""})


    def _import_landmarks(self):
        file_name = qt.QFileDialog.getOpenFileName(self, 'Import landmarks', '',"CSV File (*.csv)")
        if file_name == "":
            return
        landmark_dict = {lm.name: lm for lm in self.landmarks}
        with open(file_name, 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=';'
                                    if locale.localeconv()['decimal_point'] == "," else ",", quoting=csv.QUOTE_MINIMAL)
            for row in reader:
                try:
                    name = row['landmark name']
                    x = locale.atof(row['x'])
                    y = locale.atof(row['y'])
                    z = locale.atof(row['z'])
                except Exception as e:
                    errorDisplay("Invalid file. Must contain columns: 'landmark name', 'x', 'y', 'z'")
                    return
                if name not in landmark_dict.keys():
                    errorDisplay(f"Unknown landmark {name}")
                    return
                landmark = landmark_dict[name]
                landmark.define(x, y, z)
                # Older exports won't have a "radius" column at all, and it's only meaningful
                # for sphere landmarks - restore it only when both are present.
                radius_text = row.get('radius') if hasattr(row, 'get') else None
                if radius_text and hasattr(landmark, "set_radius"):
                    try:
                        landmark.set_radius(locale.atof(radius_text))
                    except ValueError:
                        pass
        # force update
        self.measurement_stack.currentWidget().disable() 
        self.measurement_stack.currentWidget().enable()

    def _export_measurements(self):
        file_name = qt.QFileDialog.getSaveFileName(self, 'Export measurements', '',"CSV File (*.csv)")
        if file_name == "":
            return

        with open(file_name, 'w+', newline='') as csvfile:
            fieldnames = ['measurement', 'value', 'description']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';' 
                                    if locale.localeconv()['decimal_point'] == "," else ",", quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            for i in range(self.measurement_stack.count):
                measurement = self.measurement_stack.widget(i).measurement
                result_ready, result_value, result_string = measurement()
                if result_ready:
                    writer.writerow({"measurement": measurement.name, 
                                     "value": locale.str(result_value), 
                                     "description": result_string})
        

    def _change_row(self, i):
        self.measurement_stack.currentWidget().disable()
        self.measurement_stack.setCurrentIndex(i)
        self.measurement_stack.currentWidget().enable()

    # Sphere visualization for fitted centers (femur head / condyles)
    SPHERE_COLORS = {
        "femur head": (0.9, 0.2, 0.2),
        "medial femur condyle": (0.2, 0.6, 0.9),
        "lateral femur condyle": (0.2, 0.8, 0.4),
    }

    def _sphere_node_name(self, label):
        return f"BoneAngleMeter {self.side} {label} sphere"

    def _on_show_spheres_toggled(self, checked):
        self.spheres_visible = bool(checked)
        if not self.spheres_visible:
            self.hide_all_spheres()
        else:
            # Re-show spheres for whichever measurement is currently active, if it's ready
            current_widget = self.measurement_stack.currentWidget()
            if current_widget is not None:
                current_widget.update_measurement()

    def show_sphere(self, label, center, radius):
        if not self.spheres_visible:
            self.hide_sphere(label)
            return

        node = self.sphere_nodes.get(label)
        if node is None:
            node = slicer.mrmlScene.GetFirstNodeByName(self._sphere_node_name(label))
        if node is None:
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", self._sphere_node_name(label))
            node.CreateDefaultDisplayNodes()
            display_node = node.GetDisplayNode()
            color = self.SPHERE_COLORS.get(label, (0.8, 0.8, 0.2))
            display_node.SetColor(*color)
            display_node.SetOpacity(0.35)
            display_node.SetVisibility2D(False)
        self.sphere_nodes[label] = node

        sphere_source = vtk.vtkSphereSource()
        sphere_source.SetCenter(float(center[0]), float(center[1]), float(center[2]))
        sphere_source.SetRadius(max(float(radius), 0.01))
        sphere_source.SetThetaResolution(32)
        sphere_source.SetPhiResolution(32)
        sphere_source.Update()
        node.SetAndObservePolyData(sphere_source.GetOutputDataObject(0))
        node.GetDisplayNode().SetVisibility(True)

    def hide_sphere(self, label):
        node = self.sphere_nodes.get(label)
        if node is not None and node.GetDisplayNode() is not None:
            node.GetDisplayNode().SetVisibility(False)

    def hide_all_spheres(self):
        for label in list(self.sphere_nodes.keys()):
            self.hide_sphere(label)

    def _on_show_axes_toggled(self, checked):
        self.axes_visible = bool(checked)
        if not self.axes_visible:
            self.hide_all_axes()
        else:
            current_widget = self.measurement_stack.currentWidget()
            if current_widget is not None:
                current_widget.update_measurement()

    def _axis_node_name(self, label):
        return f"BoneAngleMeter {self.side} {label} axis"

    def show_axis(self, label, start, end, color):
        if not self.axes_visible:
            self.hide_axis(label)
            return

        node = self.axis_nodes.get(label)
        if node is None:
            node = slicer.mrmlScene.GetFirstNodeByName(self._axis_node_name(label))
        if node is None:
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", self._axis_node_name(label))
            node.CreateDefaultDisplayNodes()
            display_node = node.GetDisplayNode()
            display_node.SetVisibility2D(False)
        self.axis_nodes[label] = node

        line_source = vtk.vtkLineSource()
        line_source.SetPoint1(float(start[0]), float(start[1]), float(start[2]))
        line_source.SetPoint2(float(end[0]), float(end[1]), float(end[2]))
        tube_filter = vtk.vtkTubeFilter()
        tube_filter.SetInputConnection(line_source.GetOutputPort())
        tube_filter.SetRadius(1.0)
        tube_filter.SetNumberOfSides(12)
        tube_filter.Update()
        node.SetAndObservePolyData(tube_filter.GetOutputDataObject(0))
        node.GetDisplayNode().SetColor(*color)
        node.GetDisplayNode().SetVisibility(True)

    def hide_axis(self, label):
        node = self.axis_nodes.get(label)
        if node is not None and node.GetDisplayNode() is not None:
            node.GetDisplayNode().SetVisibility(False)

    def hide_all_axes(self):
        for label in list(self.axis_nodes.keys()):
            self.hide_axis(label)

    def _on_show_labels_toggled(self, checked):
        markups_node = slicer.mrmlScene.GetNodeByID(self.markup_node_id)
        if markups_node is None:
            return
        display_node = markups_node.GetDisplayNode()
        if display_node is None:
            return
        # Different Slicer versions expose this under different names; use whichever is available.
        if hasattr(display_node, "SetPointLabelsVisibility"):
            display_node.SetPointLabelsVisibility(bool(checked))
        elif hasattr(display_node, "SetTextVisibility"):
            display_node.SetTextVisibility(bool(checked))
        else:
            display_node.SetTextScale(1.0 if checked else 0.0)

    def _delete_all_landmarks(self):
        if qt.QMessageBox.question(self, "Delete all landmarks",
                                    f"Delete all placed {self.side} landmarks? This cannot be undone.",
                                    qt.QMessageBox.Yes | qt.QMessageBox.No) != qt.QMessageBox.Yes:
            return

        current_widget = self.measurement_stack.currentWidget()
        if current_widget is not None:
            current_widget.disable()

        for landmark in self.landmarks:
            landmark._id = None
            landmark.placed = False

        markups_node = slicer.mrmlScene.GetNodeByID(self.markup_node_id)
        if markups_node is not None:
            markups_node.RemoveAllControlPoints()

        if current_widget is not None:
            current_widget.enable()

    def activate(self):
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetReferenceActivePlaceNodeID(self.markup_node_id)

        # Auto-select first item
        if self.measurement_list.currentRow == -1 and self.measurement_list.count > 0:
            # setCurrentRow triggers currentRowChanged -> _change_row, which already calls
            # enable() on the newly-selected measurement - don't call it again below, or
            # start_interaction() runs twice without an intervening stop_interaction(),
            # registering duplicate observers.
            self.measurement_list.setCurrentRow(0)
        else:
            current_widget = self.measurement_stack.currentWidget()
            if current_widget is not None:
                current_widget.enable()

    def deactivate(self):
        self.measurement_stack.currentWidget().disable()
        self.hide_all_spheres()
        self.hide_all_axes()


class MeasurementWidget(qt.QWidget):
    '''
    Widget that displays the landmarks and results of a measurement
    '''
    def __init__(self, measurement, dialog):
        super().__init__()

        self.measurement = measurement
        self.dialog = dialog
        self.enabled = False

        self.landmark_stack = qt.QStackedWidget(self)
        self.landmark_list = qt.QListWidget()
        self.next_landmark_button = qt.QPushButton("Next")
        self.prev_landmark_button = qt.QPushButton("Previous")
        self.delete_landmark_button = qt.QPushButton("Delete")
        self.delete_landmark_button.setToolTip("Delete the currently selected landmark so it can be placed again.")
        self.next_landmark_button.setDefault(True)
        self.next_landmark_button.setAutoDefault(False)
        self.prev_landmark_button.setDefault(False)
        self.prev_landmark_button.setAutoDefault(False)
        self.delete_landmark_button.setDefault(False)
        self.delete_landmark_button.setAutoDefault(False)

        self.landmark_group_box = qt.QGroupBox("Landmarks")
        self.landmark_list.setMaximumHeight(110)

        nav_row = qt.QHBoxLayout()
        nav_row.addWidget(self.prev_landmark_button)
        nav_row.addWidget(self.next_landmark_button)
        nav_row_widget = qt.QWidget()
        nav_row_widget.setLayout(nav_row)

        landmark_layout = qt.QVBoxLayout()
        landmark_layout.addWidget(self.landmark_list)
        landmark_layout.addWidget(nav_row_widget)
        landmark_layout.addWidget(self.delete_landmark_button)
        landmark_layout.addWidget(self.landmark_stack)
        self.landmark_group_box.setLayout(landmark_layout)

        self.name_label = qt.QLabel(f"<big>{self.measurement.name}</big>")
        self.name_label.setWordWrap(True)
        self.description_label = qt.QLabel(self.measurement.description)
        self.description_label.setWordWrap(True)
        self.measurement_label = qt.QLabel(f"Not available")
        self.axes_label = qt.QLabel("")
        self.axes_label.setWordWrap(True)
        
        layout = qt.QFormLayout()
        layout.addRow(self.name_label)
        layout.addRow("<b>Description</b>", self.description_label)
        layout.addRow("<b>Result</b>", self.measurement_label)
        layout.addRow("<b>Axes</b>", self.axes_label)
        layout.addRow(self.landmark_group_box)

        self.setLayout(layout)

        self.next_shortcut = qt.QShortcut(qt.QKeySequence('Return'), self)
        self.next_shortcut.activated.connect(self._next_row)
        self.next_shortcut.setContext(qt.Qt.ApplicationShortcut)

        self.prev_shortcut = qt.QShortcut(qt.QKeySequence('Shift+Return'), self)
        self.prev_shortcut.activated.connect(self._prev_row)
        self.prev_shortcut.setContext(qt.Qt.ApplicationShortcut)

        for landmark in self.measurement.get_landmarks():
            widget_cls = SphereLandmarkWidget if hasattr(landmark, "radius") else LandmarkWidget
            self.landmark_stack.addWidget(widget_cls(landmark))
            self.landmark_list.addItem(landmark.name)
            landmark.add_change_callback(self.update_measurement)

        self.landmark_list.currentRowChanged.connect(self._change_row)
        self.next_landmark_button.clicked.connect(self._next_row)
        self.prev_landmark_button.clicked.connect(self._prev_row)
        self.delete_landmark_button.clicked.connect(self._delete_current_landmark)

        self.update_measurement()

    def enable(self):
        # Auto-select first item
        if self.landmark_list.currentRow == -1 and self.landmark_list.count > 0:
            # Emit signal currentRowChanged
            self.landmark_list.setCurrentRow(0)

        for landmark in self.measurement.landmarks:
            landmark.show()
        
        current_landmark_widget = self.landmark_stack.currentWidget()
        current_landmark_widget.landmark.start_interaction()
                   
        self.next_shortcut.setEnabled(True)
        self.prev_shortcut.setEnabled(True)
        self.enabled = True

        self.update_measurement()
        
    def disable(self):
        for landmark in self.measurement.landmarks:
            landmark.stop_interaction()
            landmark.hide()
        self.next_shortcut.setEnabled(False)
        self.prev_shortcut.setEnabled(False)
        self.enabled = False
        for label in self.measurement.SPHERE_LABELS:
            self.dialog.hide_sphere(label)
        for label in self.measurement.AXIS_LABELS:
            self.dialog.hide_axis(label)

    def update_measurement(self):
        if self.enabled:
            try:
                result_ready, result_value, result_string = self.measurement()
                if result_ready:
                    self.measurement_label.setText(f"{result_value:.2f}\N{DEGREE SIGN} {result_string}")
                    self.measurement_label.setStyleSheet("QLabel { background-color : green}")
                    for label, (center, radius) in self.measurement.get_spheres().items():
                        self.dialog.show_sphere(label, center, radius)
                    axis_items = list(self.measurement.get_axes().items())
                    legend_parts = []
                    for i, (label, (start, end)) in enumerate(axis_items):
                        color = self.dialog.AXIS_PALETTE[i % len(self.dialog.AXIS_PALETTE)]
                        self.dialog.show_axis(label, start, end, color)
                        r, g, b = [int(round(c * 255)) for c in color]
                        legend_parts.append(f'<span style="color:rgb({r},{g},{b})">&#9632;</span> {label}')
                    self.axes_label.setText("<br>".join(legend_parts))
                else:
                    self.measurement_label.setText(result_string)
                    self.measurement_label.setStyleSheet("QLabel { background-color : orange}")
                    self.axes_label.setText("")
                    for label in self.measurement.SPHERE_LABELS:
                        self.dialog.hide_sphere(label)
                    for label in self.measurement.AXIS_LABELS:
                        self.dialog.hide_axis(label)
            except Exception as e:
                self.measurement_label.setText(f"Error executing measurement: {e}")
                self.measurement_label.setStyleSheet("QLabel { background-color : red}")
                self.axes_label.setText("")
                for label in self.measurement.SPHERE_LABELS:
                    self.dialog.hide_sphere(label)
                for label in self.measurement.AXIS_LABELS:
                    self.dialog.hide_axis(label)

    # Internal callbacks
    def _next_row(self):
        if self.landmark_list.currentRow + 1 < self.landmark_list.count:
            # Emit signal currentRowChanged
            self.landmark_list.setCurrentRow(self.landmark_list.currentRow + 1)

    def _prev_row(self):
        if self.landmark_list.currentRow > 0:
            # Emit signal currentRowChanged
            self.landmark_list.setCurrentRow(self.landmark_list.currentRow - 1)

    def _change_row(self, i):
        old_landmark_widget = self.landmark_stack.currentWidget()
        old_landmark_widget.landmark.stop_interaction()
        self.landmark_stack.setCurrentIndex(i)
        new_landmark_widget = self.landmark_stack.currentWidget()
        new_landmark_widget.landmark.start_interaction()

    def _delete_current_landmark(self):
        current_landmark_widget = self.landmark_stack.currentWidget()
        if current_landmark_widget is None:
            return
        landmark = current_landmark_widget.landmark
        landmark.stop_interaction()
        landmark.delete()
        landmark.start_interaction()

class LandmarkWidget(qt.QWidget):
    '''
    Info-box for landmarks
    '''
    def __init__(self, landmark):
        super(LandmarkWidget, self).__init__()

        self.landmark = landmark

        self.landmark_label = qt.QLabel(f"<big>{self.landmark.name}</big>")
        self.landmark_label.setWordWrap(True)
        self.description_label = qt.QLabel(self.landmark.description)
        self.description_label.setWordWrap(True)
        self.position_label = qt.QLabel("Position: not set")
        if self.landmark.image_path != "":
            path = osp.join(MODULE_PATH, self.landmark.image_path)
            pixmap = qt.QPixmap(path)
            if pixmap.isNull():
                raise ValueError(f"Could not load image from file '{path}'")
            self.image = ResizableImage(pixmap)
        else:
            self.image = None

        layout = qt.QVBoxLayout()
        layout.addWidget(self.landmark_label)
        layout.addWidget(self.description_label)
        layout.addWidget(self.position_label)
        if self.image is not None:
            layout.addWidget(self.image)
            layout.setStretch(layout.count()-1, 1)
        self.setLayout(layout)

        self.landmark.add_change_callback(self._update_position_label)
        self._update_position_label()

    def _update_position_label(self):
        if self.landmark.placed:
            p = self.landmark.get_position()
            self.position_label.setText(f"Position: {p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f} mm")
        else:
            self.position_label.setText("Position: not set")


class SphereLandmarkWidget(LandmarkWidget):
    '''
    Info-box for a SphereLandmark: adds a radius control on top of the usual position/description
    panel, so the user can place the center point and then manually grow/shrink the sphere (drawn
    live in the 3D view) until it visually matches the bone surface.
    '''
    def __init__(self, landmark):
        super().__init__(landmark)

        self.radius_spinbox = qt.QDoubleSpinBox()
        self.radius_spinbox.setRange(1.0, 100.0)
        self.radius_spinbox.setSingleStep(0.5)
        self.radius_spinbox.setSuffix(" mm")
        self.radius_spinbox.setValue(landmark.radius)
        self.radius_spinbox.setToolTip(
            "Adjust the sphere's radius in the 3D view until it best matches the condyle surface.")
        self.radius_spinbox.valueChanged.connect(self._on_radius_changed)

        # Put the radius spinbox on the same row as the position readout, instead of its own
        # separate row, for a more compact layout.
        insert_index = self.layout().indexOf(self.position_label)
        self.layout().removeWidget(self.position_label)

        position_radius_row = qt.QHBoxLayout()
        position_radius_row.addWidget(self.position_label, 1)
        position_radius_row.addWidget(qt.QLabel("Radius"))
        position_radius_row.addWidget(self.radius_spinbox)
        position_radius_row_widget = qt.QWidget()
        position_radius_row_widget.setLayout(position_radius_row)

        self.layout().insertWidget(insert_index, position_radius_row_widget)

    def _on_radius_changed(self, value):
        self.landmark.set_radius(value)


class ResizableImage(qt.QLabel):
    """
    Widget that displays an image scaled once to a fixed target width, keeping aspect ratio.
    Deliberately not dynamically responsive to container resizing - trying to negotiate width via
    size policies and height-for-width proved unreliable across Slicer's Qt/stylesheet
    environment (repeatedly caused the sidebar to be forced wider than the screen). A fixed
    target width that comfortably fits Slicer's typical sidebar is far more robust. Click the
    image to view it larger in a popup.
    """
    TARGET_WIDTH = 260  # px - adjust here if it's still too wide/narrow for your sidebar
    POPUP_MAX_WIDTH = 900
    POPUP_MAX_HEIGHT = 700

    def __init__(self, pixmap) -> None:
        super().__init__()
        self.raw_pixmap = pixmap
        self.setPixmap(self.raw_pixmap.scaled(
            qt.QSize(self.TARGET_WIDTH, 100000), qt.Qt.KeepAspectRatio, qt.Qt.SmoothTransformation))
        self.setAlignment(qt.Qt.AlignCenter)
        self.setCursor(qt.Qt.PointingHandCursor)
        self.setToolTip("Click to view full size")
        self._popup = None

    def mousePressEvent(self, event):
        self._show_popup()
        event.accept()

    def _show_popup(self):
        # Reuse the existing popup (just bring it to front) instead of stacking up duplicates
        # if the image is clicked more than once.
        if self._popup is not None:
            self._popup.raise_()
            self._popup.activateWindow()
            return

        popup = qt.QDialog(self)
        popup.setWindowTitle("Landmark reference image")

        pixmap = self.raw_pixmap
        if pixmap.width() > self.POPUP_MAX_WIDTH or pixmap.height() > self.POPUP_MAX_HEIGHT:
            pixmap = pixmap.scaled(qt.QSize(self.POPUP_MAX_WIDTH, self.POPUP_MAX_HEIGHT),
                                    qt.Qt.KeepAspectRatio, qt.Qt.SmoothTransformation)

        image_label = qt.QLabel()
        image_label.setPixmap(pixmap)
        image_label.setAlignment(qt.Qt.AlignCenter)

        layout = qt.QVBoxLayout()
        layout.addWidget(image_label)
        popup.setLayout(layout)

        # Non-modal: lets the user keep it open while placing landmarks in the 3D view.
        popup.finished.connect(self._on_popup_closed)
        self._popup = popup
        popup.show()

    def _on_popup_closed(self):
        self._popup = None