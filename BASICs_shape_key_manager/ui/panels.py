import bpy
from bpy.types import Panel

class SHAPEKEY_PT_manager(Panel):
    """BASICs Shape Key Manager Panel"""
    bl_label = "BASICs Shape Key Manager"
    bl_idname = "SHAPEKEY_PT_manager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BASIC"
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if obj and obj.type == 'MESH':
            # Basic shape key operations section
            box = layout.box()
            box.label(text="Basic Operations")
            
            if obj.data.shape_keys:
                col = box.column(align=True)
                row = col.row(align=True)
                row.operator("shapekey.copy_values")
                row.operator("shapekey.cut_values")
                
                row = col.row()
                row.operator("shapekey.paste_values")
                
                # Add mirror buttons if there are shape keys
                # For active shape key mirroring, require an active non-basis shape key
                if obj.active_shape_key_index > 0:  # Index 0 is Basis
                    row = col.row()
                    row.operator("shapekey.mirror")
                # Mirror All Missing button - always available if any shape keys exist
                row = col.row()
                row.operator("shapekey.mirror_all_missing")
                
                # Add mirror tolerance setting
                row = col.row()
                row.prop(context.scene, "shapekey_mirror_tolerance", slider=True)
                
                # Add the remove selected vertices operator (only in edit mode)
                if obj.mode == 'EDIT':
                    row = col.row()
                    row.operator("shapekey.remove_selected_vertices")
                
                col.separator()
                
                row = col.row()
                row.operator("shapekey.save_values")
                
                row = col.row()
                row.operator("shapekey.load_values")
                
                # Display number of active shape keys
                num_keys = len(obj.data.shape_keys.key_blocks) - 1  # Subtract 1 for the Basis shape
                col.label(text=f"Active Shape Keys: {num_keys}")
            else:
                box.label(text="No Shape Keys on selected object")
            
            # Mesh Operations section (new)
            box = layout.box()
            box.label(text="Mesh Operations")
            
            col = box.column(align=True)
            row = col.row()
            row.operator("mesh.force_mirror")
            
            # Additional UI for advanced mesh settings
            if context.scene.get("mesh_mirror_show_advanced", False):
                row = col.row()
                row.prop(context.scene, "mesh_mirror_show_advanced", toggle=True, text="Hide Advanced")
                
                # Show advanced options if we have them defined
                if hasattr(context.scene, "mesh_mirror_center_tolerance"):
                    row = col.row()
                    row.prop(context.scene, "mesh_mirror_center_tolerance")
                if hasattr(context.scene, "mesh_mirror_move_center_vertices"):
                    row = col.row()
                    row.prop(context.scene, "mesh_mirror_move_center_vertices")
            else:
                row = col.row()
                row.prop(context.scene, "mesh_mirror_show_advanced", toggle=True, text="Show Advanced")
            
            # Vertex Group operations section
            box = layout.box()
            box.label(text="Vertex Group Operations")
            
            if len(obj.vertex_groups) > 0:
                col = box.column(align=True)
                row = col.row()
                row.operator("vertexgroup.combine_groups")
                
                row = col.row()
                row.operator("vertexgroup.remove_empty")
                
                # Display number of vertex groups
                col.label(text=f"Vertex Groups: {len(obj.vertex_groups)}")
            else:
                box.label(text="No Vertex Groups on selected object")
            
            # Advanced shape key operations section
            box = layout.box()
            box.label(text="Shape Key Transfer")
            
            # Source & target info
            if len(context.selected_objects) < 2:
                box.label(text="Select source then target (active)")
            else:
                sources = [o for o in context.selected_objects if o != obj and o.type == 'MESH']
                if sources:
                    source_names = ", ".join([s.name for s in sources[:3]])
                    if len(sources) > 3:
                        source_names += f" and {len(sources) - 3} more"
                    box.label(text=f"Source: {source_names}")
                    box.label(text=f"Target: {obj.name} (active)")
                    
                    # Show transfer settings in the panel
                    col = box.column(align=True)
                    col.prop(context.scene, "shapekey_transfer_strength", slider=True)
                    col.prop(context.scene, "shapekey_transfer_clear_existing")
                    col.prop(context.scene, "shapekey_transfer_skip_minimal")
                    
                    # Only show threshold if skip_minimal_effect is enabled
                    if context.scene.shapekey_transfer_skip_minimal:
                        col.prop(context.scene, "shapekey_transfer_threshold", slider=True)
                    
                    # Transfer button
                    col = box.column(align=True)
                    has_sources_with_shapekeys = any(s.data.shape_keys for s in sources if s.type == 'MESH')
                    if has_sources_with_shapekeys:
                        col.operator("shapekey.transfer_with_surface_deform")
                    else:
                        col.label(text="Source has no shape keys")
        elif obj and obj.type == 'ARMATURE':
            # Armature Operations section
            box = layout.box()
            box.label(text="Armature Operations")
            
            col = box.column(align=True)
            
            # Check/Fix Armature Modifiers button - always available
            row = col.row()
            row.operator("armature.check_fix_modifiers")
            
            # Show operator only in edit mode
            if obj.mode == 'EDIT':
                col.separator()
                row = col.row()
                op = row.operator("armature.delete_other_bones")
                op.preserve_children = True
                
                row = col.row()
                row.label(text="Select bones to keep, others will be deleted")
                
                row = col.row()
                row.label(text="Parents and children of selected bones are preserved")
                
                col.separator()
            else:
                col.label(text="Enter Edit Mode to access bone operations")
        else:
            layout.label(text="Select a mesh or armature object")