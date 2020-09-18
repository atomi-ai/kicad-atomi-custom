import pcbnew
from pcbnew import ToMM as ToUnit
#from pcbnew import ToMils as ToUnit
import re
import sys
from collections import defaultdict

board = pcbnew.LoadBoard(sys.argv[1])
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

                component_type[fp] += 1
                print(f"{m.GetReference()}, {fp}, {m.GetValue()}, "
                      f"{ToUnit(m.GetPosition()[0])}, {ToUnit(m.GetPosition()[1])}, {m.GetOrientationDegrees()}", file=f)

        print('#Component types:', len(component_type), file=f)
        print('#Total component number:', sum(component_type.values()), file=f)
        f.close()


def export_coordinate_jlc():
    for layer_name in export_layers:
        layer_id = layertable[layer_name]

        f_coord = open(f"{layer_name}_coordinate.csv", 'w')
        f_bom = open(f"{layer_name}_bom.csv", 'w')
        component_type = defaultdict(int)
        component_names = defaultdict(list)
        component_comment = defaultdict(str)

        print("Designator,Footprint,Qty,Comment,LCSC", file=f_bom)
        print("Designator,Package,Val,Mid X,Mid Y,Layer,Rotation", file=f_coord)
        
        for m in board.GetModules():
            if m.GetLayer() == layer_id:
                fpid = m.GetFPID()
                fp = f"{fpid.GetLibNickname().wx_str()}:{fpid.GetLibItemName().wx_str()}"
                key = f"{fp}:{m.GetValue()}"
                if [x for x in skip_pkg if x.lower() in fp.lower()]:
                    continue
                if [x for x in skip_value if x.lower() in m.GetValue().lower()]:
                    continue

                component_type[key] += 1
                component_names[key].append(m.GetReference())
                component_comment[key] = m.GetValue()
                print(f"{m.GetReference()}, {fp}, {m.GetValue()}, "
                      f"{ToUnit(m.GetPosition()[0])}, {ToUnit(m.GetPosition()[1])}, {export_layers[layer_name]}, {m.GetOrientationDegrees()}", file=f_coord)

        d=', '
        for k in component_type:
            print(f'"{d.join(component_names[k])}", {k}, {component_type[k]}, {component_comment[k]},', file=f_bom)

        f_bom.close()
        f_coord.close()


if __name__ == "__main__":
    export_coordinate_jlc()
