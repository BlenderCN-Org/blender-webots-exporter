# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

# Inspired by the x3d exporter of bart:neeneenee*de, http://www.neeneenee.de/vrml, Campbell Barton
# refrence: https://github.com/sobotka/blender-addons/blob/master/io_scene_x3d/export_x3d.py

"""
This script exports to Webots format.
Usage:
Run this script from "File->Export" menu.  A pop-up will ask whether you
want to export only selected or all relevant objects.
Known issues:
    Doesn't handle multiple materials (don't use material indices);<br>
    Doesn't handle multiple UV textures on a single mesh (create a mesh for each texture);<br>
    Can't get the texture array associated with material * not the UV ones;
"""

import math
import os

import bpy
import mathutils

from bpy_extras.io_utils import create_derived_objects, free_derived_objects


def clight_color(col):
    return tuple([max(min(c, 1.0), 0.0) for c in col])


def matrix_direction_neg_z(matrix):
    return (matrix.to_3x3() * mathutils.Vector((0.0, 0.0, -1.0))).normalized()[:]


def prefix_string(value, prefix):
    return prefix + value


def suffix_string(value, suffix):
    return value + suffix


def bool_as_str(value):
    return ('FALSE', 'TRUE')[bool(value)]


def clean_def(txt):
    # see report [#28256]
    if not txt:
        txt = "None"
    # no digit start
    if txt[0] in "1234567890+-":
        txt = "_" + txt
    return txt.translate({
        # control characters 0x0-0x1f
        # 0x00: "_",
        0x01: "_",
        0x02: "_",
        0x03: "_",
        0x04: "_",
        0x05: "_",
        0x06: "_",
        0x07: "_",
        0x08: "_",
        0x09: "_",
        0x0a: "_",
        0x0b: "_",
        0x0c: "_",
        0x0d: "_",
        0x0e: "_",
        0x0f: "_",
        0x10: "_",
        0x11: "_",
        0x12: "_",
        0x13: "_",
        0x14: "_",
        0x15: "_",
        0x16: "_",
        0x17: "_",
        0x18: "_",
        0x19: "_",
        0x1a: "_",
        0x1b: "_",
        0x1c: "_",
        0x1d: "_",
        0x1e: "_",
        0x1f: "_",

        0x7f: "_",  # 127

        0x20: "_",  # space
        0x22: "_",  # "
        0x27: "_",  # '
        0x23: "_",  # #
        0x2c: "_",  # ,
        0x2e: "_",  # .
        0x5b: "_",  # [
        0x5d: "_",  # ]
        0x5c: "_",  # \
        0x7b: "_",  # {
        0x7d: "_"  # }
    })


def build_hierarchy(objects):
    """ Returns parent child relationships, skipping. """
    objects_set = set(objects)
    par_lookup = {}

    def test_parent(parent):
        while (parent is not None) and (parent not in objects_set):
            parent = parent.parent
        return parent

    for obj in objects:
        par_lookup.setdefault(test_parent(obj.parent), []).append((obj, []))

    for parent, children in par_lookup.items():
        for obj, subchildren in children:
            subchildren[:] = par_lookup.get(obj, [])

    return par_lookup.get(None, [])


# -----------------------------------------------------------------------------
# Functions for writing output file
# -----------------------------------------------------------------------------

def export(file,
           global_matrix,
           scene,
           use_mesh_modifiers=False,
           use_selection=True,
           use_hierarchy=True,
           path_mode='AUTO',
           name_decorations=True,
           ):

    # -------------------------------------------------------------------------
    # Global Setup
    # -------------------------------------------------------------------------
    import bpy_extras
    from bpy_extras.io_utils import unique_name
    from xml.sax.saxutils import escape

    if name_decorations:
        # If names are decorated, the uuid map can be split up
        # by type for efficiency of collision testing
        # since objects of different types will always have
        # different decorated names.
        uuid_cache_object = {}    # object
        uuid_cache_light = {}      # 'LA_' + object.name
        uuid_cache_view = {}      # object, different namespace
        uuid_cache_mesh = {}      # mesh
        uuid_cache_material = {}  # material
        uuid_cache_image = {}     # image
        uuid_cache_world = {}     # world
        CA_ = 'CA_'
        OB_ = 'OB_'
        ME_ = 'ME_'
        IM_ = 'IM_'
        WO_ = 'WO_'
        MA_ = 'MA_'
        LA_ = 'LA_'
        group_ = 'group_'
    else:
        # If names are not decorated, it may be possible for two objects to
        # have the same name, so there has to be a unified dictionary to
        # prevent uuid collisions.
        uuid_cache = {}
        uuid_cache_object = uuid_cache           # object
        uuid_cache_light = uuid_cache             # 'LA_' + object.name
        uuid_cache_view = uuid_cache             # object, different namespace
        uuid_cache_mesh = uuid_cache             # mesh
        uuid_cache_material = uuid_cache         # material
        uuid_cache_image = uuid_cache            # image
        uuid_cache_world = uuid_cache            # world
        del uuid_cache
        CA_ = ''
        OB_ = ''
        ME_ = ''
        IM_ = ''
        WO_ = ''
        MA_ = ''
        LA_ = ''
        group_ = ''

    _TRANSFORM = '_TRANSFORM'

    # store files to copy
    copy_set = set()

    # store names of newly cerated meshes, so we dont overlap
    mesh_name_set = set()

    fw = file.write
    base_src = os.path.dirname(bpy.data.filepath)
    base_dst = os.path.dirname(file.name)

    # -------------------------------------------------------------------------
    # File Writing Functions
    # -------------------------------------------------------------------------

    def writeHeader():
        fw('#VRML_SIM R2019a utf8\n')
        fw('WorldInfo {\n')
        fw('}\n')
        fw('Viewpoint {\n')
        fw('orientation -0.5 -0.852 -0.159 0.71\n')
        fw('position -3.6 2.0 5.4\n')
        fw('}\n')
        fw('TexturedBackground {\n')
        fw('}\n')
        fw('TexturedBackgroundLight {\n')
        fw('}\n')

    def writeFooter():
        pass

    def writeTransform_begin(matrix, def_id):
        if def_id is not None:
            fw('DEF %s ' % def_id)
        fw('Transform {\n')

        loc, rot, sca = matrix.decompose()
        rot = rot.to_axis_angle()
        rot = (*rot[0], rot[1])

        fw('translation %.6f %.6f %.6f\n' % loc[:])
        fw('scale %.6f %.6f %.6f\n' % sca[:])
        fw('rotation %.6f %.6f %.6f %.6f\n' % rot)
        fw('children [\n')

    def writeTransform_end():
        fw(']\n')
        fw('}\n')

    def writeIndexedFaceSet(obj, mesh, matrix, world):
        obj_id = unique_name(obj, OB_ + obj.name, uuid_cache_object, clean_func=clean_def, sep="_")
        mesh_id = unique_name(mesh, ME_ + mesh.name, uuid_cache_mesh, clean_func=clean_def, sep="_")
        mesh_id_group = prefix_string(mesh_id, group_)
        mesh_id_coords = prefix_string(mesh_id, 'coords_')

        # tessellation faces may not exist
        if not mesh.tessfaces and mesh.polygons:
            mesh.update(calc_tessface=True)

        if not mesh.tessfaces:
            return

        # use _ifs_TRANSFORM suffix so we dont collide with transform node when
        # hierarchys are used.
        writeTransform_begin(matrix, suffix_string(obj_id, "_ifs" + _TRANSFORM))

        if mesh.tag:
            fw('USE %s {}}\n' % (mesh_id_group))
        else:
            mesh.tag = True

            fw('DEF %s Group {\n' % (mesh_id_group))
            fw('children [\n')

            is_uv = bool(mesh.tessface_uv_textures.active)
            is_coords_written = False

            mesh_materials = mesh.materials[:]
            if not mesh_materials:
                mesh_materials = [None]

            mesh_material_tex = [None] * len(mesh_materials)
            mesh_material_mtex = [None] * len(mesh_materials)
            mesh_material_images = [None] * len(mesh_materials)

            for i, material in enumerate(mesh_materials):
                if material:
                    for mtex in material.texture_slots:
                        if mtex:
                            tex = mtex.texture
                            if tex and tex.type == 'IMAGE':
                                image = tex.image
                                if image:
                                    mesh_material_tex[i] = tex
                                    mesh_material_mtex[i] = mtex
                                    mesh_material_images[i] = image
                                    break

            mesh_materials_use_face_texture = [getattr(material, 'use_face_texture', True) for material in mesh_materials]

            # fast access!
            mesh_faces = mesh.tessfaces[:]
            mesh_faces_materials = [f.material_index for f in mesh_faces]
            mesh_faces_vertices = [f.vertices[:] for f in mesh_faces]

            if is_uv and True in mesh_materials_use_face_texture:
                mesh_faces_image = [(fuv.image
                                     if mesh_materials_use_face_texture[mesh_faces_materials[i]]
                                     else mesh_material_images[mesh_faces_materials[i]])
                                     for i, fuv in enumerate(mesh.tessface_uv_textures.active.data)]

                mesh_faces_image_unique = set(mesh_faces_image)
            elif len(set(mesh_material_images) | {None}) > 1:  # make sure there is at least one image
                mesh_faces_image = [mesh_material_images[material_index] for material_index in mesh_faces_materials]
                mesh_faces_image_unique = set(mesh_faces_image)
            else:
                mesh_faces_image = [None] * len(mesh_faces)
                mesh_faces_image_unique = {None}

            # group faces
            face_groups = {}
            for material_index in range(len(mesh_materials)):
                for image in mesh_faces_image_unique:
                    face_groups[material_index, image] = []
            del mesh_faces_image_unique

            for i, (material_index, image) in enumerate(zip(mesh_faces_materials, mesh_faces_image)):
                face_groups[material_index, image].append(i)

            # same as face_groups.items() but sorted so we can get predictable output.
            face_groups_items = list(face_groups.items())
            face_groups_items.sort(key=lambda m: (m[0][0], getattr(m[0][1], 'name', '')))

            for (material_index, image), face_group in face_groups_items:  # face_groups.items()
                if face_group:
                    material = mesh_materials[material_index]

                    fw('Shape {\n')

                    is_smooth = False

                    # kludge but as good as it gets!
                    for i in face_group:
                        if mesh_faces[i].use_smooth:
                            is_smooth = True
                            break

                    # UV's and VCols split verts off which effects smoothing
                    # force writing normals in this case.
                    # Also, creaseAngle is not supported for IndexedTriangleSet,
                    # so write normals when is_smooth (otherwise
                    # IndexedTriangleSet can have only all smooth/all flat shading).
                    fw('appearance PBRAppearance {\n')

                    if image:
                        writeImageTexture(image)

                    if material:
                        emit = material.emit
                        diffuseColor = material.diffuse_color[:]
                        if world:
                            ambiColor = ((material.ambient * 2.0) * world.ambient_color)[:]
                        else:
                            ambiColor = 0.0, 0.0, 0.0

                        emitColor = tuple(((c * emit) + ambiColor[i]) / 2.0 for i, c in enumerate(diffuseColor))
                        transp = material.alpha

                        fw('baseColor %.3f %.3f %.3f\n' % clight_color(diffuseColor))
                        fw('emissiveColor %.3f %.3f %.3f\n' % clight_color(emitColor))
                        fw('metalness 0\n')
                        fw('roughness 0.5\n')
                        fw('transparency %s\n' % transp)

                    fw('}\n')  # -- PBRAppearance

                    mesh_faces_uv = mesh.tessface_uv_textures.active.data if is_uv else None

                    fw('geometry IndexedFaceSet {\n')

                    # --- Write IndexedFaceSet Attributes (same as IndexedTriangleSet)
                    fw('solid %s\n' % bool_as_str(material and material.game_settings.use_backface_culling))
                    if is_smooth:
                        # use Auto-Smooth angle, if enabled. Otherwise make
                        # the mesh perfectly smooth by creaseAngle > pi.
                        fw('creaseAngle %.4f\n' % (mesh.auto_smooth_angle if mesh.use_auto_smooth else 1.0))

                    # for IndexedTriangleSet we use a uv per vertex so this isnt needed.
                    if is_uv:
                        fw('texCoordIndex [\n')

                        j = 0
                        for i in face_group:
                            if len(mesh_faces_vertices[i]) == 4:
                                fw('%d %d %d %d -1 ' % (j, j + 1, j + 2, j + 3))
                                j += 4
                            else:
                                fw('%d %d %d -1 ' % (j, j + 1, j + 2))
                                j += 3
                        fw(']\n')
                        # --- end texCoordIndex

                    if True:
                        fw('coordIndex [')
                        for i in face_group:
                            fv = mesh_faces_vertices[i]
                            if len(fv) == 3:
                                fw('%i %i %i -1 ' % fv)
                            else:
                                fw('%i %i %i %i -1 ' % fv)

                        fw(']\n')
                        # --- end coordIndex

                    # --- Write IndexedFaceSet Elements
                    if True:
                        if is_coords_written:
                            fw('coord USE=%s\n' % (mesh_id_coords))
                        else:
                            fw('coord ')
                            fw('DEF %s ' % mesh_id_coords)
                            fw('Coordinate {\n')
                            fw('point [')
                            for v in mesh.vertices:
                                fw('%.6f %.6f %.6f ' % v.co[:])
                            fw(']\n')
                            fw('}\n')

                            is_coords_written = True

                    if is_uv:
                        fw('texCoord TextureCoordinate [')
                        for i in face_group:
                            for uv in mesh_faces_uv[i].uv:
                                fw('%.4f %.4f ' % uv[:])
                        del mesh_faces_uv
                        fw(']\n')

                    # --- output vertexColors

                    # --- output closing braces
                    fw('}\n')  # --- IndexedFaceSet
                    fw('}\n')  # --- Shape
            fw(']\n')  # --- Group
            fw('}\n')  # --- Group
        writeTransform_end()

    def writeImageTexture(image):
        image_id = unique_name(image, IM_ + image.name, uuid_cache_image, clean_func=clean_def, sep="_")

        if image.tag:
            fw('texture USE=%s\n' % (image_id))
        else:
            image.tag = True

            fw('texture ')
            fw('DEF %s ' % image_id)
            fw('ImageTexture {\n')

            # collect image paths, can load multiple
            # [relative, name-only, absolute]
            filepath = image.filepath
            filepath_full = bpy.path.abspath(filepath, library=image.library)
            filepath_ref = bpy_extras.io_utils.path_reference(filepath_full, base_src, base_dst, path_mode, "textures", copy_set, image.library)
            filepath_base = os.path.basename(filepath_full)

            images = [
                filepath_ref,
                filepath_base,
            ]
            if path_mode != 'RELATIVE':
                images.append(filepath_full)

            images = [f.replace('\\', '/') for f in images]
            images = [f for i, f in enumerate(images) if f not in images[:i]]

            fw('url [ "%s" ]\n' % ' '.join(['"%s"' % escape(f) for f in images]))
            fw('}\n')

    # -------------------------------------------------------------------------
    # Export Object Hierarchy (recursively called)
    # -------------------------------------------------------------------------
    def export_object(obj_main_parent, obj_main, obj_children):
        matrix_fallback = mathutils.Matrix()
        world = scene.world
        free, derived = create_derived_objects(scene, obj_main)

        if use_hierarchy:
            obj_main_matrix_world = obj_main.matrix_world
            if obj_main_parent:
                obj_main_matrix = obj_main_parent.matrix_world.inverted(matrix_fallback) * obj_main_matrix_world
            else:
                obj_main_matrix = obj_main_matrix_world
            obj_main_matrix_world_invert = obj_main_matrix_world.inverted(matrix_fallback)

            obj_main_id = unique_name(obj_main, obj_main.name, uuid_cache_object, clean_func=clean_def, sep="_")

            writeTransform_begin(obj_main_matrix if obj_main_parent else global_matrix * obj_main_matrix, suffix_string(obj_main_id, _TRANSFORM))

        for obj, obj_matrix in (() if derived is None else derived):
            obj_type = obj.type

            if use_hierarchy:
                # make transform node relative
                obj_matrix = obj_main_matrix_world_invert * obj_matrix
            else:
                obj_matrix = global_matrix * obj_matrix

            if obj_type in {'MESH', 'CURVE', 'SURFACE', 'FONT'}:
                if (obj_type != 'MESH') or (use_mesh_modifiers and obj.is_modified(scene, 'PREVIEW')):
                    try:
                        me = obj.to_mesh(scene, use_mesh_modifiers, 'PREVIEW')
                    except:
                        me = None
                    do_remove = True
                else:
                    me = obj.data
                    do_remove = False

                if me is not None:
                    # ensure unique name, we could also do this by
                    # postponing mesh removal, but clearing data - TODO
                    if do_remove:
                        me.name = obj.name.rstrip("1234567890").rstrip(".")
                        me_name_new = me_name_org = me.name
                        count = 0
                        while me_name_new in mesh_name_set:
                            me.name = "%.17s.%03d" % (me_name_org, count)
                            me_name_new = me.name
                            count += 1
                        mesh_name_set.add(me_name_new)
                        del me_name_new, me_name_org, count
                    # done

                    writeIndexedFaceSet(obj, me, obj_matrix, world)

                    # free mesh created with create_mesh()
                    if do_remove:
                        bpy.data.meshes.remove(me)

            else:
                # print('Info: Ignoring [%s], object type [%s] not handle yet' % (object.name,object.getType))
                pass

        if free:
            free_derived_objects(obj_main)

        # ---------------------------------------------------------------------
        # write out children recursively
        # ---------------------------------------------------------------------
        for obj_child, obj_child_children in obj_children:
            export_object(obj_main, obj_child, obj_child_children)

        if use_hierarchy:
            writeTransform_end()

    # -------------------------------------------------------------------------
    # Main Export Function
    # -------------------------------------------------------------------------
    def export_main():
        # tag un-exported IDs
        bpy.data.meshes.tag(False)
        bpy.data.materials.tag(False)
        bpy.data.images.tag(False)

        if use_selection:
            objects = [obj for obj in scene.objects if obj.is_visible(scene) and obj.select]
        else:
            objects = [obj for obj in scene.objects if obj.is_visible(scene)]

        print('Info: starting Webots export to %r...' % file.name)
        writeHeader()

        if use_hierarchy:
            objects_hierarchy = build_hierarchy(objects)
        else:
            objects_hierarchy = ((obj, []) for obj in objects)

        for obj_main, obj_main_children in objects_hierarchy:
            export_object(None, obj_main, obj_main_children)

        writeFooter()

    export_main()

    # -------------------------------------------------------------------------
    # global cleanup
    # -------------------------------------------------------------------------
    file.close()

    # copy all collected files.
    # print(copy_set)
    bpy_extras.io_utils.path_reference_copy(copy_set)

    print('Info: finished Webots export to %r' % file.name)


##########################################################
# Callbacks, needed before Main
##########################################################

def save(context, filepath, *,
         use_selection=True,
         use_mesh_modifiers=False,
         use_hierarchy=True,
         global_matrix=None,
         path_mode='AUTO',
         name_decorations=True):

    bpy.path.ensure_ext(filepath, '.wbt')

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')

    file = open(filepath, 'w', encoding='utf-8')

    if global_matrix is None:
        global_matrix = mathutils.Matrix()

    export(
        file,
        global_matrix,
        context.scene,
        use_mesh_modifiers=use_mesh_modifiers,
        use_selection=use_selection,
        use_hierarchy=use_hierarchy,
        path_mode=path_mode,
        name_decorations=name_decorations
    )

    return {'FINISHED'}
