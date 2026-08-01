/* views.jsx — barrel for the main-area views (split into views/).
   Keeps the top-level module name so the build entry and app.jsx imports
   stay unchanged; the actual components live in views/<area>.jsx. */
import { CalendarView, MemoryPage, TasksView, TeamView, VIEW_LABELS } from './views/core.jsx';
import { VaultView } from './views/vault.jsx';
import { GraphView } from './views/graph.jsx';
import { ComingSoon, TerminalView } from './views/misc.jsx';
import { ProjectsView, WorkspaceView } from './views/projects.jsx';

const CafresoHQViews = {
  TasksView,
  MemoryPage,
  TeamView,
  CalendarView,
  VaultView,
  GraphView,
  ComingSoon,
  ProjectsView,
  WorkspaceView,
  TerminalView,
  VIEW_LABELS,
};

export { CafresoHQViews };
