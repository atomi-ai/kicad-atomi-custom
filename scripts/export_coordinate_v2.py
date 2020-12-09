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


class KicadBoard:
    def __init__(self, board_file_name: str):
        self.board = pcbnew.LoadBoard(board_file_name)
        self.ori_x, self.ori_y = self.board.GetAuxOrigin()
        print(f"aux ori:{self.ori_x}, {self.ori_y}")
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
        # if skip_bottom:
        #     del export_layers['B.Cu']
        self.export_layer_ids = [self.layertable[x] for x in self.export_layers]

    # bb = board.ComputeBoundingBox()
    # skip_pkg += ['tht', 'conn', 'jumper', 'mountinghole', 'transformer', 'my_footprint', 'my_component', 'testpoint', 'project_footprints']
    # skip_value += ['dni']

    def iter_part(self):
        for layer_name in self.export_layers:
            layer_id = self.layertable[layer_name]
            layer_tag = self.export_layers[layer_name]

            # f_coord = open(f"{layer_name}_coordinate.csv", 'w')
            # f_bom = open(f"{layer_name}_bom.csv", 'w')
            component_type = defaultdict(int)
            component_names = defaultdict(list)
            component_comment = defaultdict(str)
            component_pins = defaultdict(str)

            for m in self.board.GetModules():
                if m.GetLayer() == layer_id:
                    fpid = m.GetFPID()
                    fp = f"{fpid.GetLibNickname().wx_str()}:{fpid.GetLibItemName().wx_str()}" if fpid.GetLibNickname().wx_str() else f"{fpid.GetLibItemName().wx_str()}"
                    key = f"{fp}:{m.GetValue()}"
                    # if [x for x in skip_pkg if x.lower() in fp.lower()]:
                    #     continue
                    # if [x for x in skip_value if x.lower() in m.GetValue().lower()]:
                    #     continue

                    component_type[key] += 1
                    component_names[key].append(m.GetReference())
                    component_comment[key] = m.GetValue()
                    component_pins[key] = m.GetPadCount()
                    pos_x, pos_y = self.convert_coord(m.GetPosition())
                    first_pad = m.Pads().GetFirst()
                    pad_x, pad_y = self.convert_coord(first_pad.GetPosition())
                    # pad_x = first_pad.GetPosition()[0] - self.ori_x
                    # pad_y = self.ori_y - first_pad.GetPosition()[1]

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
                # via_x = ToUnit(int(t.GetPosition()[0] - self.ori_x))
                # via_y = ToUnit(int(self.ori_y - t.GetPosition()[1]))
                via_drill = ToUnit(int(t.GetDrill()))
                via = DrillHole(via_x, via_y, via_drill, True)
                yield via

    def iter_pad(self):
        for p in self.board.GetPads():
            if p.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_CIRCLE:
                drill_size = ToUnit(p.GetDrillSize()[0])
                if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD and drill_size > 0:
                    drill_x, drill_y = self.convert_coord(p.GetPosition())
                    drill = DrillHole(drill_x, drill_y, drill_size, p.GetAttribute() != pcbnew.PAD_ATTRIB_HOLE_NOT_PLATED)
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


def export_drill_gcode():
    parser = argparse.ArgumentParser(description='export kicad pcb board component values')
    parser.add_argument('kicad_pcb_filename')
    parser.add_argument('--jlc', nargs=1, help='export_jlc_name')
    parser.add_argument('--ickey', nargs=1, help='export_ickey_name')
    parser.add_argument('--drill', nargs=1, help='export_drill_name')
    args = parser.parse_args()

    board = KicadBoard(args.kicad_pcb_filename)
    if args.drill is not None:
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
        os.system(f"unix2dos {export_fn}")


if __name__ == "__main__":
    export_drill_gcode()
