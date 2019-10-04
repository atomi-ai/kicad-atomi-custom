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

export_layers=[
    'F.Cu',
#    'B.Cu'
]
export_layer_ids = [layertable[x] for x in export_layers]

bb = board.ComputeBoundingBox()


skip_pkg = ['tht', 'conn', 'jumper', 'mountinghole', 'transformer', 'my_footprint', 'my_component', 'testpoint']
skip_value = ['dni', 'TRAFO-147']
for layer_name in export_layers:
    layer_id = layertable[layer_name]

    f = open(f"{layer_name}.csv",'w')
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
