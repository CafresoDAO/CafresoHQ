import { CanistersView } from './views/canisters.jsx';
/* views.jsx — barrel for the main-area views (split into views/).
   Keeps the top-level module name so the build entry and app.jsx imports
   stay unchanged; the actual components live in views/<area>.jsx. */
import { MemoryPage, TasksView, TeamView, VIEW_LABELS } from './views/core.jsx';
import { VaultView } from './views/vault.jsx';
import { GraphView } from './views/graph.jsx';
import { TerminalView } from './views/misc.jsx';
import { ProjectsView, WorkspaceView } from './views/projects.jsx';
import { MarketView } from './views/market.jsx';

const CafresoHQViews = {
  TasksView,
  MemoryPage,
  TeamView,
  VaultView,
  GraphView,
  ProjectsView,
  WorkspaceView,
  TerminalView,
  MarketView,
  VIEW_LABELS,
};

export {
  CanistersView, CafresoHQViews };
