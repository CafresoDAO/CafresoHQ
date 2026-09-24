import re

with open('graph-engine.js', 'r') as f:
    content = f.read()

events_replacement = """  _wireEvents() {
    const r = this.renderer;
    r.on('enterNode', ({ node }) => { this.hovered = node; this._nbrCache = null; this._refreshReducers(); this._emit('hover', node); });
    r.on('leaveNode', () => { this.hovered = null; this._nbrCache = null; this._refreshReducers(); this._emit('hover', null); });
    r.on('clickNode', ({ node }) => { this.selected = node; this._nbrCache = null; this._refreshReducers(); this._emit('nodeClick', node); });
    r.on('rightClickNode', (e) => { if (e.event && e.event.original) e.event.original.preventDefault(); this._emit('nodeRightClick', e.node, e.event); });
    r.on('doubleClickNode', ({ node }) => this._emit('nodeDoubleClick', node));
    r.on('clickStage', () => { this.selected = null; this._nbrCache = null; this._refreshReducers(); this._emit('stageClick'); });

    // Node Dragging Implementation
    let draggedNode = null;
    let isDragging = false;
    
    r.on('downNode', (e) => {
      isDragging = true;
      draggedNode = e.node;
      r.getCamera().disable();
    });
    
    r.getMouseCaptor().on('mousemovebody', (e) => {
      if (!isDragging || !draggedNode) return;
      const pos = r.viewportToGraph(e);
      this.graph.setNodeAttribute(draggedNode, 'x', pos.x);
      this.graph.setNodeAttribute(draggedNode, 'y', pos.y);
      e.preventSigmaDefault();
      if (e.original && e.original.preventDefault) e.original.preventDefault();
      if (e.original && e.original.stopPropagation) e.original.stopPropagation();
    });
    
    const handleUp = () => {
      if (isDragging || draggedNode) {
        isDragging = false;
        draggedNode = null;
        r.getCamera().enable();
      }
    };
    
    r.getMouseCaptor().on('mouseup', handleUp);
    r.getMouseCaptor().on('dragleave', handleUp);
  }"""

content = re.sub(r'  _wireEvents\(\) \{.*?\n  \}', events_replacement, content, flags=re.DOTALL)

with open('graph-engine.js', 'w') as f:
    f.write(content)
