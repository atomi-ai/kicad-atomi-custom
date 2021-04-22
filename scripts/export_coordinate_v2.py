import pcbnew
from pcbnew import ToMM as ToUnit
from pcbnew import FromMM as FromUnit
from typing import List, Tuple
import math
import argparse
import re, sys
import os.path
from collections import defaultdict, namedtuple
from itertools import chain, groupby
from datetime import datetime

Part = namedtuple('Part', ['ref', 'footprint', 'value', 'mid_x', 'mid_y', 'ref_x', 'ref_y', 'pad_x', 'pad_y', 'layer', 'rotation', 'pad_count'])
DrillHole = namedtuple('Drill', ['x', 'y', 'size', 'plate'])


class SMT_ABS_CONF:
    groupby_func = lambda self, x: (x.footprint, x.value, x.layer)
    ordered_func = lambda self, x: x.ref

    bom_map = {'designator': lambda x:'"{}"'.format(', '.join(y.ref for y in x)),
               'footprint': lambda x:x[0].footprint,
               'quantity': lambda x:len(x),
               'comment': lambda x: x[0].value,
               'pins':lambda x:x[0].pad_count
               }

    coord_map = {'designator': lambda x:x.ref,
                 'package': lambda x:x.footprint,
                 'mid_x': lambda x:x.mid_x,
                 'mid_y': lambda x:x.mid_y,
                 'layer': lambda x:x.layer,
                 'rotation': lambda x:x.rotation,
                 'value': lambda x:x.value
                 }

    def __init__(self):
        self.renaming()
    
    def renaming(self, name_mapping={'designator':'Designator',
                                     'footprint':'Footprint',
                                     'quantity': 'Quantity',
                                     'comment': 'Comment',
                                     'pins': 'Pins',
                                     'package': 'Package',
                                     'mid_x': 'Mid X',
                                     'mid_y': 'Mid Y',
                                     'layer': 'Layer',
                                     'rotation': 'Rotation',
                                     'value': 'Val',
                                     }):
        def rename(d, old, new, pd):
            try:
                d[new] = d[old]
                del d[old]
                if d[new] is None:
                    d[new] = pd[old]
            except:
                pass
            
        for oldname, newname in name_mapping.items():
            rename(self.coord_map, oldname, newname, self.__class__.__base__.coord_map)
            rename(self.bom_map, oldname, newname, self.__class__.__base__.bom_map)

    def process_on_group(self, g):
        return [f(g) for f in self.bom_map.values()]

    def process_on_part(self, p):
        return [f(p) for f in self.coord_map.values()]

    def bom_header(self):
        return ", ".join(self.bom_map.keys())

    def coord_header(self):
        return ", ".join(self.coord_map.keys())


class SMT_JLC_CONF(SMT_ABS_CONF):
    pass

class SMT_ICKEY_CONF(SMT_ABS_CONF):
    def renaming(self, name_mapping={'designator':'Ref',
                                     'footprint':'Footprint',
                                     'quantity': 'Quantity',
                                     'comment': 'Comment',
                                     'pins': 'Pins',
                                     'package': 'Package',
                                     'mid_x': 'X',
                                     'mid_y': 'Y',
                                     'layer': 'Layer',
                                     'rotation': 'Orientation',
                                     'value': 'Value',
                                     }):
        super().renaming(name_mapping)

class SMT_MYSMT_CONF(SMT_ABS_CONF):
    coord_map = {'designator': None,
                 'package': None,
                 'mid_x': None,
                 'mid_y': None,
                 'ref_x': lambda x:x.ref_x,
                 'ref_y': lambda x:x.ref_y,
                 'pad_x': lambda x:x.pad_x,
                 'pad_y': lambda x:x.pad_y,
                 'layer': None,
                 'rotation': None,
                 'value': None
                 }
    def renaming(self, name_mapping={'designator':'Designator',
                                     'footprint':'Footprint',
                                     'quantity': 'Quantity',
                                     'comment': 'Comment',
                                     'pins': 'Pins',
                                     'package': 'Package',
                                     'mid_x': 'Mid X',
                                     'mid_y': 'Mid Y',
                                     'ref_x': 'Ref X',
                                     'ref_y': 'Ref Y',
                                     'pad_x': 'Pad X',
                                     'pad_y': 'Pad Y',                                     
                                     'layer': 'Layer',
                                     'rotation': 'Rotation',
                                     'value': 'Comment',
                                     }):
        super().renaming(name_mapping)

class KicadBoard:
    def __init__(self, board_file_name: str,
                 skip_bottom: bool = False,
                 skip_package = ['tht', 'conn', 'jumper', 'mountinghole', 'transformer', 'my_footprint', 'my_component', 'testpoint', 'project_footprints'],
                 skip_value = ['dni']):
        self.board = pcbnew.LoadBoard(board_file_name)
        self.ori_x, self.ori_y = self.board.GetDesignSettings().m_AuxOrigin
        self.layertable = {}
        numlayers = pcbnew.PCB_LAYER_ID_COUNT

        for i in range(numlayers):
            self.layertable[self.board.GetLayerName(i)] = i

        self.shape_table = {}
        for s in [x for x in dir(pcbnew) if re.match("S_.*", x)]:
            self.shape_table[getattr(pcbnew, s)] = s

        self.export_layers={
            'F.Cu':'top',
            'B.Cu':'bottom'
        }
        if skip_bottom:
            del export_layers['B.Cu']
        self.export_layer_ids = [self.layertable[x] for x in self.export_layers]

        self.bb = self.board.ComputeBoundingBox()
        self.skip_package = skip_package
        self.skip_value = skip_value

    def iter_part(self, apply_filter: bool = True):
        for layer_name in self.export_layers:
            layer_id = self.layertable[layer_name]
            layer_tag = self.export_layers[layer_name]

            component_type = defaultdict(int)
            component_names = defaultdict(list)
            component_comment = defaultdict(str)
            component_pins = defaultdict(str)

            mods = self.board.GetFootprints()
            for m in mods:
                if m.GetLayer() == layer_id:
                    fpid = m.GetFPID()
                    fp = f"{fpid.GetLibNickname().wx_str()}:{fpid.GetLibItemName().wx_str()}" if fpid.GetLibNickname().wx_str() else f"{fpid.GetLibItemName().wx_str()}"
                    key = f"{fp}:{m.GetValue()}"
                    if [x for x in self.skip_package if x.lower() in fp.lower()]:
                        continue
                    if [x for x in self.skip_value if x.lower() in m.GetValue().lower()]:
                        continue

                    component_type[key] += 1
                    component_names[key].append(m.GetReference())
                    component_comment[key] = m.GetValue()
                    component_pins[key] = m.GetPadCount()
                    pos_x, pos_y = self.convert_coord(m.GetPosition())
                    pad = m.Pads()
                    first_pad = m.Pads()[0]
                    pad_x, pad_y = self.convert_coord(first_pad.GetPosition())

                    part = Part(ref=m.GetReference(),
                                footprint=fp,
                                value=m.GetValue(),
                                mid_x=pos_x,
                                mid_y=pos_y,
                                ref_x=pos_x,
                                ref_y=pos_y,
                                pad_x=pad_x,
                                pad_y=pad_y,
                                layer=layer_tag,
                                rotation=m.GetOrientationDegrees(),
                                pad_count=m.GetPadCount())
                    yield part

    def iter_via(self):
        for t in self.board.GetTracks():
            if t.GetClass() == 'VIA': # is via
                via_x, via_y = self.convert_coord(t.GetPosition())
                via_drill = ToUnit(int(t.GetDrill()))
                via = DrillHole(via_x, via_y, via_drill, True)
                yield via

    def iter_pad(self):
        for p in self.board.GetPads():
            if p.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_CIRCLE:
                drill_size = ToUnit(p.GetDrillSize()[0])
                if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD and drill_size > 0:
                    drill_x, drill_y = self.convert_coord(p.GetPosition())
                    plated = pcbnew.PAD_ATTRIB_NPTH
                    drill = DrillHole(drill_x, drill_y, drill_size, p.GetAttribute() != plated)
                    yield drill

    def convert_coord(self, p):
        x = ToUnit(int(p[0] - self.ori_x))
        y = ToUnit(int(self.ori_y - p[1]))
        return x, y

    def nearby_sort(self, seq: List[Tuple[float, float]], key=lambda x:x):
        def distance(a, b):
            if a is None:
                return math.sqrt(b[0]**2 + b[1]**2)
            return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)
        current = None
        result = []
        nullable_key = lambda x: key(x) if x is not None else x
        while seq:
            value, idx = sorted([(distance(nullable_key(current), nullable_key(x)), n) for n, x in enumerate(seq)],
                                key=lambda x:x[0])[0]
            current = seq.pop(idx)
            result.append(current)
        return result


def append_suffix(fn: str, ext: str) -> str:
    _f, _e = os.path.splitext(fn)
    if not _e:
        return f"{_f}.{ext}"
    else:
        return fn


def unix2dos(fn):
    with open(fn, 'rb') as f:
        lines = [x.strip() for x in f.readlines()]
    with open(fn, 'wb') as f:
        f.write(b"\r\n".join(lines))


def dispatch_drill(args):
    board = KicadBoard(args.kicad_pcb_filename)
    export_fn = append_suffix(args.drill[0], 'nc')
    with open(export_fn, 'w') as f:
        f.write(f'''; exported by {sys.argv[0]}
; original pcb filename: {args.kicad_pcb_filename}
; exported date:{datetime.now()}
G90 G80 G17 G40 G00
G54 G90 S8000 M03 
G04 P5
; G69
; G68 X0 Y0 R10
Z50

''')
        drills = list(chain(board.iter_pad(), board.iter_via()))
        # group by drill size
        drills.sort(key=lambda x: x.size)

        gid = 1
        for k, g in groupby(drills, key=lambda x: x.size):
            if gid != 1:    # pause spindle
                f.write(f'G00 Z50 M05\nM01\n')
            f.write(f'T{gid} (C{k}) M06\n')
            if gid != 1:    # restart spindle
                f.write(f'M03\nG04 P5\n')

            gid += 1
            ordered_drills = board.nearby_sort(list(g), key=lambda x:(x.x, x.y))
            first = True

            for d in ordered_drills:
                if first:
                    f.write(f'X{d.x} Y{d.y} Z4\nG81 R4 Z-1 F80\n')
                    first = False
                else:
                    f.write(f'X{d.x} Y{d.y}\n')
            f.write(f'G80\n')
        f.write(f'M5\n')
    unix2dos(export_fn)


def dispatch_smt(out_fn, pcb_fn, export_conf):
    board = KicadBoard(pcb_fn)
    parts = list(board.iter_part())

    parts.sort(key=export_conf.groupby_func)
    bom = []
    coord = []
    component_type = defaultdict(int)
    total_pads = 0
    for k, g in groupby(parts, key=export_conf.groupby_func):
        g_lst = list(g)
        ordered_parts = sorted(g_lst, key=export_conf.ordered_func)
        for p in g_lst:
            component_type[p.footprint] += 1
            total_pads += p.pad_count
        bom.append(export_conf.process_on_group(g_lst))
        coord.extend(export_conf.process_on_part(x) for x in g_lst)
    with open(append_suffix(out_fn+"_bom", 'csv'), 'w') as f_bom:
        f_bom.write(export_conf.bom_header() + '\n')
        f_bom.write('\n'.join(', '.join(str(x) for x in line) for line in bom))
    with open(append_suffix(out_fn+'_coord', 'csv'), 'w') as f_coord:
        f_coord.write(export_conf.coord_header() + '\n')
        f_coord.write('\n'.join(', '.join(str(x) for x in line) for line in coord))


    print(f"#Board width:{ToUnit(board.bb.GetWidth())} height:{ToUnit(board.bb.GetHeight())}")
    print(f'#Total component number:{sum(component_type.values())}')
    print(f'#Total pads number:{total_pads}')

def export_main():
    parser = argparse.ArgumentParser(description='export kicad pcb board component values')
    parser.add_argument('kicad_pcb_filename')
    parser.add_argument('--jlc', nargs=1, help='export_jlc_name')
    parser.add_argument('--ickey', nargs=1, help='export_ickey_name')
    parser.add_argument('--mysmt', nargs=1, help='export_mysmt_name')
    parser.add_argument('--drill', nargs=1, help='export_drill_name')
    args = parser.parse_args()

    if args.drill is not None:
        dispatch_drill(args)
    if args.jlc is not None:
        dispatch_smt(args.jlc[0], args.kicad_pcb_filename, SMT_JLC_CONF())
    if args.ickey is not None:
        dispatch_smt(args.ickey[0], args.kicad_pcb_filename, SMT_ICKEY_CONF())
    if args.mysmt is not None:
        dispatch_smt(args.mysmt[0], args.kicad_pcb_filename, SMT_MYSMT_CONF())

if __name__ == "__main__":
    export_main()
