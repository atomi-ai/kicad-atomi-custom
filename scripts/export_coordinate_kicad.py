import pcbnew
from pcbnew import ToMM as ToUnit
from pcbnew import FromMM as FromUnit
#from pcbnew import ToMils as ToUnit
import re
import sys
from typing import List
from collections import defaultdict, namedtuple
import numpy as np
CaliPoints = namedtuple("CaliPoints", ['po_x', 'po_y', 'pr_x', 'pr_y'])
Point = namedtuple('Point', ['x', 'y'])

board = pcbnew.LoadBoard(sys.argv[1])
ori_x, ori_y = board.GetAuxOrigin()
layertable = {}
numlayers = pcbnew.PCB_LAYER_ID_COUNT
for i in range(numlayers):
    layertable[board.GetLayerName(i)] = i

shape_table = {}
for s in [x for x in dir(pcbnew) if re.match("S_.*", x)]:
    shape_table[getattr(pcbnew, s)] = s

export_layers={
    'F.Cu':'top',
#    'B.Cu':'bottom'
}
export_layer_ids = [layertable[x] for x in export_layers]

bb = board.ComputeBoundingBox()
skip_pkg = ['tht', 'conn', 'jumper', 'mountinghole', 'transformer', 'my_footprint', 'my_component', 'testpoint', 'project_footprints']
skip_value = ['dni', 'TRAFO-147']


def export_coordinate_ickey():
    total_pads = 0
    for layer_name in export_layers:
        layer_id = layertable[layer_name]

        f = open(f"{layer_name}.csv", 'w')
        print(f"#Side: {layer_name}", file=f)
        print(f"#Unit: MM", file=f)
        print(f"#Board width:{ToUnit(bb.GetWidth())} height:{ToUnit(bb.GetHeight())}", file=f)
        print(f"#Board xy:{ToUnit(bb.GetX())}, {ToUnit(bb.GetY())}", file=f)
        component_type = defaultdict(int)
        component_smd = defaultdict(int)

        print("Ref, Footprint, Value, X, Y, Orientation", file=f)
        for m in board.GetModules():
            if m.GetLayer() == layer_id:
                fpid = m.GetFPID()
                fp = f"{fpid.GetLibNickname().wx_str()}:{fpid.GetLibItemName().wx_str()}"
                if [x for x in skip_pkg if x.lower() in fp.lower()]:
                    continue
                if [x for x in skip_value if x.lower() in m.GetValue().lower()]:
                    continue

                total_pads += m.GetPadCount() 
                component_type[fp] += 1
                print(f"{m.GetReference()}, {fp}, {m.GetValue()}, "
                      f"{ToUnit(m.GetPosition()[0]-ori_x)}, {ToUnit(m.GetPosition()[1]-ori_y)}, {m.GetOrientationDegrees()}", file=f)

        print('#Component types:', len(component_type), file=f)
        print('#Total component number:', sum(component_type.values()), file=f)
        print('#Total pads number:', total_pads, file=f)
        f.close()


def export_coordinate_jlc(my_smt=False, calibration=None, delta=None, limit=None):
    if calibration is not None:
        import affine6p
        datas = np.array(calibration)
        src = datas[:, :2]
        dst = datas[:, 2:]
        trans = affine6p.estimate(src, dst)
    else:
        trans = None
        
    for layer_name in export_layers:
        layer_id = layertable[layer_name]
        layer_tag = export_layers[layer_name] if not my_smt else export_layers[layer_name][0].upper()

        f_coord = open(f"{layer_name}_coordinate.csv", 'w')
        f_bom = open(f"{layer_name}_bom.csv", 'w')
        component_type = defaultdict(int)
        component_names = defaultdict(list)
        component_comment = defaultdict(str)
        component_pins = defaultdict(str)

        print("Designator,Footprint,Quantity,Comment,Pins", file=f_bom)
        if my_smt:
            print("Designator,Footprint,Mid X,Mid Y,Ref X,Ref Y,Pad X,Pad Y, Layer,Rotation,Comment", file=f_coord)
        else:
            print("Designator,Package,Mid X,Mid Y,Layer,Rotation,Val", file=f_coord)
        
        for m in board.GetModules():
            if m.GetLayer() == layer_id:
                fpid = m.GetFPID()
                fp = f"{fpid.GetLibNickname().wx_str()}:{fpid.GetLibItemName().wx_str()}" if fpid.GetLibNickname().wx_str() else f"{fpid.GetLibItemName().wx_str()}"
                key = f"{fp}:{m.GetValue()}"
                if [x for x in skip_pkg if x.lower() in fp.lower()]:
                    continue
                if [x for x in skip_value if x.lower() in m.GetValue().lower()]:
                    continue

                component_type[key] += 1
                component_names[key].append(m.GetReference())
                component_comment[key] = m.GetValue()
                component_pins[key] = m.GetPadCount() 
                raw_pos_x = m.GetPosition()[0] - ori_x
                raw_pos_y = ori_y - m.GetPosition()[1]
                first_pad = m.Pads().GetFirst()
                raw_pad_x = first_pad.GetPosition()[0] - ori_x
                raw_pad_y = ori_y - first_pad.GetPosition()[1]
                if trans:
                    pos_x, pos_y= trans.transform((raw_pos_x, raw_pos_y))
                    pad_x, pad_y = trans.transform((raw_pad_x, raw_pad_y))
                else:
                    pos_x, pos_y = raw_pos_x, raw_pos_y
                    pad_x, pad_y = raw_pad_x, raw_pad_y
                if delta is not None:
                    pos_x += FromUnit(delta[0])
                    pos_y += FromUnit(delta[1])
                    pad_x += FromUnit(delta[0])
                    pad_y += FromUnit(delta[1])

                if limit:
                    if pos_x > FromUnit(limit[0]) or pos_y > FromUnit(limit[1]):
                        continue
                print(f'"{m.GetReference()}", "{fp}", '
                      f'"{ToUnit(int(pos_x))}mm", "{ToUnit(int(pos_y))}mm",'        # Mid
                      f'"{ToUnit(int(pos_x))}mm", "{ToUnit(int(pos_y))}mm",'        # Ref
                      f'"{ToUnit(int(pad_x))}mm", "{ToUnit(int(pad_y))}mm",'        # Pad
                      f'"{layer_tag}", "{m.GetOrientationDegrees()}", "{m.GetValue()}"', file=f_coord)

        d=', '
        for k in component_type:
            print(f'"{d.join(component_names[k])}", {k}, {component_type[k]}, {component_comment[k]},{component_pins[k]}', file=f_bom)

        f_bom.close()
        f_coord.close()


if __name__ == "__main__":
    #export_coordinate_ickey(#my_smt=True,
    export_coordinate_jlc(#my_smt=True,
                          # calibration=[CaliPoints(337.5, 342.6, 337.351, 342.224),
                          #              CaliPoints(0, 342.5, -0.302, 341.324),
                          #              CaliPoints(342.6, 0, 342.718, 1.058)],
                          # delta=(0, 0.5),
                          # limit=(335, 380),
    )
