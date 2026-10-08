"""Draw the expanded campus graph in the original black-map style.

Run: python draw_map.py
"""
import pickle
import io
import sys
import webbrowser
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import networkx as nx


def draw(graph_path=None, output_path=None, show=False):
    folder = Path(__file__).parent
    graph_path = Path(graph_path) if graph_path else folder / 'utd_graph.pkl'
    output_path = Path(output_path) if output_path else folder / 'utd_routes.png'
    with graph_path.open('rb') as file:
        graph = pickle.load(file)
    from academic_routing import academic_only, academic_routes
    graph = academic_only(graph)
    fig, ax = plt.subplots(figsize=(8, 8), facecolor='#111111')
    ax.set_facecolor('#111111')
    lines = []
    for start, end, edge in graph.edges(data=True):
        shape = edge.get('geometry')
        lines.append(list(shape.coords) if shape is not None else
                     [(graph.nodes[start]['x'], graph.nodes[start]['y']),
                      (graph.nodes[end]['x'], graph.nodes[end]['y'])])
    ax.add_collection(LineCollection(lines, colors='#999999', linewidths=1, zorder=1))
    # Use the original walking graph's extent so adding labels does not reframe it.
    walk = [d for _, d in graph.nodes(data=True) if d.get('type') == 'path']
    minx, maxx = min(d['x'] for d in walk), max(d['x'] for d in walk)
    miny, maxy = min(d['y'] for d in walk), max(d['y'] for d in walk)
    dx, dy = (maxx - minx) * .02, (maxy - miny) * .02
    ax.set_xlim(minx - dx, maxx + dx)
    ax.set_ylim(miny - dy, maxy + dy)
    import math
    ax.set_aspect(1 / math.cos(math.radians((maxy + miny) / 2)))
    display_routes = graph.graph.get('academic_display_routes')
    if display_routes is None:
        _, display_routes = academic_routes(graph)
    for i, connection in enumerate(display_routes):
        start, end, route = connection['start'], connection['end'], connection['path']
        color = ['red', 'yellow', 'cyan'][i % 3]
        coordinates = []
        for a, b in zip(route, route[1:]):
            edge = min(graph[a][b].values(), key=lambda e: e['length'])
            shape = edge.get('geometry')
            coordinates.extend(list(shape.coords) if shape is not None else
                               [(graph.nodes[a]['x'], graph.nodes[a]['y']), (graph.nodes[b]['x'], graph.nodes[b]['y'])])
        ax.plot(*zip(*coordinates), color=color, linewidth=4, alpha=.5, zorder=3)
    label_offsets = {
        'ML2': (-25, 4), 'ML1': (4, -12), 'NB': (8, -3), 'NL': (4, 9),
        'CB': (6, -12), 'PHA': (-25, -11), 'PHY': (-28, 1),
        'JO': (4, 9), 'TH': (4, -13), 'FN': (-24, -9),
        'BE': (-20, -12), 'FA': (4, 4), 'FO': (4, -11),
    }
    for node, data in graph.nodes(data=True):
        if data.get('category') in ('academic', 'parking'):
            color = 'orange' if data.get('category') == 'parking' else 'deepskyblue'
            ax.scatter(data['x'], data['y'], c=color, s=40, zorder=5)
            ax.annotate(str(node), (data['x'], data['y']), color='white', fontsize=8,
                        xytext=label_offsets.get(node, (4, 4)), textcoords='offset points', zorder=6)
    ax.set_axis_off()
    fig.savefig(output_path, dpi=200, bbox_inches='tight', facecolor=fig.get_facecolor())
    buffer = io.StringIO()
    fig.savefig(buffer, format='svg', bbox_inches='tight', facecolor=fig.get_facecolor())
    svg = buffer.getvalue()
    svg = svg[svg.index('<svg'):]
    interactive_path = output_path.with_name('utd_map.html')
    interactive_path.write_text(INTERACTIVE_HTML.replace('__MAP__', svg), encoding='utf-8')
    plt.close(fig)
    print(f'Saved {output_path}: {sum(d.get("type") in ("building", "parking") for _, d in graph.nodes(data=True))} labeled nodes')
    print(f'Interactive map: {interactive_path}')
    if show:
        webbrowser.open(interactive_path.resolve().as_uri())


INTERACTIVE_HTML = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UTD academic map — zoom and pan</title><style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#111;color:white;font:14px Arial,sans-serif}
#map{width:100%;height:100%}#map>svg{display:block;width:100%;height:100%;touch-action:none;cursor:grab}#map>svg:active{cursor:grabbing}
.tools{position:fixed;top:12px;left:12px;z-index:10;display:flex;align-items:center;gap:8px;background:#222e;padding:8px;border-radius:5px}
button{background:#333;border:1px solid #666;color:white;border-radius:3px;padding:7px 12px;cursor:pointer;font-size:15px}button:hover{background:#555}
span{font-size:12px;color:#ccc}@media(max-width:600px){span{display:none}}
</style></head><body><div class="tools"><button id="in" aria-label="Zoom in">+</button><button id="out" aria-label="Zoom out">−</button><button id="reset">Reset</button><span>Scroll to zoom · Drag to pan</span></div><div id="map">__MAP__</div>
<script>
const svg=document.querySelector('#map>svg'),initial=svg.getAttribute('viewBox').split(/\\s+/).map(Number);let box=[...initial],drag=null;
function render(){svg.setAttribute('viewBox',box.join(' '))}
function point(e){let p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;return p.matrixTransform(svg.getScreenCTM().inverse())}
function zoom(f,p={x:box[0]+box[2]/2,y:box[1]+box[3]/2}){let w=Math.max(initial[2]/1000,Math.min(initial[2]*4,box[2]*f)),h=box[3]*w/box[2];box=[p.x-(p.x-box[0])*w/box[2],p.y-(p.y-box[1])*h/box[3],w,h];render()}
document.getElementById('in').onclick=()=>zoom(.75);document.getElementById('out').onclick=()=>zoom(1.333);document.getElementById('reset').onclick=()=>{box=[...initial];render()};
svg.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY>0?1.15:1/1.15,point(e))},{passive:false});
svg.addEventListener('pointerdown',e=>{if(e.button!==0)return;drag=point(e);svg.setPointerCapture(e.pointerId)});
svg.addEventListener('pointermove',e=>{if(!drag)return;let p=point(e);box[0]+=drag.x-p.x;box[1]+=drag.y-p.y;render()});
svg.addEventListener('pointerup',e=>{drag=null;if(svg.hasPointerCapture(e.pointerId))svg.releasePointerCapture(e.pointerId)});svg.addEventListener('pointercancel',()=>{drag=null});
</script></body></html>'''


if __name__ == '__main__':
    draw(show='--show' in sys.argv)
