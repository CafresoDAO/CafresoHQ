import { MSG_STATES } from './windows.jsx';
import { whoCan } from './agents.jsx';
import { CafresoHQUI } from '../ui.jsx';
const { useCommands } = CafresoHQUI;
function AppGlobalCommands({
  /* `navigate`, not setActiveView. Every one of these eight entries used
     the raw setter, which in windowed (desktop) mode is a SILENT no-op —
     so the command palette's whole Navigation section moved the breadcrumb
     and opened nothing. The host passes `navTo`, which opens/raises the
     window on desktop and falls back to the plain setter on mobile. */
  activeView, navigate,
  night, setNight,
  railCollapsed, setRailCollapsed,
  chatWinOpen, setChatWinOpen,
  density, setDensity,
  theme, setTheme,
  windowsEnabled, setWindowsEnabled, onOpenWindow,
  workspaces = [], activeWorkspace, onApplyWorkspace, onSaveWorkspace, onDeleteWorkspace,
  onHire, onSettings, onMissions, onWorkflow, onStandup, onMemory, onStopAll,
  anyBusy,
  agents = [], chat = [], onDmAgent, onJumpToMessage,
  // Phase 2 comms props — open the inbox with a pre-applied filter, or
  // re-dispatch a failed message. Optional; commands no-op gracefully
  // when they aren't provided.
  onOpenInbox, onRetryFailed, messages = [],
}) {
  const cmds = [
    /* Switch view — one entry per nav item. */
    { id: 'nav.office',     label: 'Switch view: Office',    section: 'Navigation', icon: '🏢', run: () => navigate('visual') },
    { id: 'nav.tasks',      label: 'Switch view: Tasks',     section: 'Navigation', icon: '📋', run: () => navigate('tasks') },
    { id: 'nav.calendar',   label: 'Switch view: Calendar',  section: 'Navigation', icon: '🗓', run: () => navigate('calendar') },
    { id: 'nav.memory',     label: 'Switch view: Memory',    section: 'Navigation', icon: '📁', run: () => navigate('memory') },
    { id: 'nav.vault',      label: 'Switch view: Vault',     section: 'Navigation', icon: '📓', run: () => navigate('vault') },
    { id: 'nav.team',       label: 'Switch view: Team',      section: 'Navigation', icon: '👥', run: () => navigate('team') },
    { id: 'nav.terminal',   label: 'Switch view: Terminal',  section: 'Navigation', icon: '☼', run: () => navigate('terminal') },
    { id: 'nav.projects',   label: 'Switch view: Projects',  section: 'Navigation', icon: '🗂', run: () => navigate('projects') },

    /* Top-level actions. */
    { id: 'act.hire',     label: 'Hire a new coworker',         section: 'Actions', icon: '＋', run: onHire },
    { id: 'act.standup',  label: 'Run end-of-day stand-up',  section: 'Actions', icon: '🌅', run: onStandup },
    { id: 'act.missions', label: 'Open research missions',   section: 'Actions', icon: '🔬', run: onMissions },
    { id: 'act.workflow', label: 'New workflow',             section: 'Actions', icon: '⚡', run: onWorkflow },
    { id: 'act.memory',   label: 'Open memory shelf',        section: 'Actions', icon: '📁', run: onMemory },
    { id: 'act.settings', label: 'Open settings',            section: 'Actions', icon: '⚙', shortcut: ['⌘', ','], run: onSettings },
    { id: 'act.stop-all', label: 'Stop everyone + every night shift', section: 'Actions', icon: '■', run: onStopAll, when: anyBusy },

    /* Toggles. */
    { id: 'tog.night',
      label: night ? 'Switch to day mode' : 'Switch to night mode',
      section: 'Toggles', icon: night ? '☀' : '☾',
      run: () => setNight(v => !v),
    },
    { id: 'tog.rail',
      label: railCollapsed ? 'Expand sidebar' : 'Collapse sidebar',
      section: 'Toggles', icon: railCollapsed ? '»' : '«',
      run: () => setRailCollapsed(v => !v),
    },
    { id: 'tog.desktop',
      label: windowsEnabled ? 'Exit desktop (window) mode' : 'Enable desktop (window) mode',
      section: 'Toggles', icon: '🪟',
      run: () => setWindowsEnabled && setWindowsEnabled(v => !v),
    },
    /* Open a specific app as a window (desktop mode). */
    ...(onOpenWindow ? [
      ['tasks','Tasks'],['memory','Memory'],['team','Team'],['calendar','Calendar'],
      ['vault','Vault'],['projects','Workspace'],['terminal','Terminal'],
    ].map(([v, lbl]) => ({
      id: 'win.open.' + v, label: 'Open in window: ' + lbl, section: 'Windows', icon: '🪟',
      run: () => onOpenWindow(v),
    })) : []),
    { id: 'tog.chat',
      label: chatWinOpen ? 'Close chat window' : 'Open chat window',
      section: 'Toggles', icon: '💬',
      run: () => setChatWinOpen(v => !v),
      when: activeView === 'projects' || activeView === 'vault',
    },

    /* Density. */
    { id: 'dens.comfortable', label: 'Density: Comfortable (default)', section: 'Density', icon: '◯',
      run: () => setDensity('comfortable'), when: density !== 'comfortable' },
    { id: 'dens.compact',     label: 'Density: Compact',               section: 'Density', icon: '◗',
      run: () => setDensity('compact'),     when: density !== 'compact' },
    { id: 'dens.spacious',    label: 'Density: Spacious',              section: 'Density', icon: '◯',
      run: () => setDensity('spacious'),    when: density !== 'spacious' },

    /* Themes. */
    { id: 'thm.default',      label: 'Theme: Warm pastel (default)', section: 'Theme', icon: '🎨',
      run: () => setTheme('default'),     when: theme !== 'default' },
    { id: 'thm.sepia',        label: 'Theme: Sepia',                 section: 'Theme', icon: '📜',
      run: () => setTheme('sepia'),       when: theme !== 'sepia' },
    { id: 'thm.solarized',    label: 'Theme: Solarized',             section: 'Theme', icon: '☀',
      run: () => setTheme('solarized'),   when: theme !== 'solarized' },
    { id: 'thm.dracula',      label: 'Theme: Dracula',               section: 'Theme', icon: '🦇',
      run: () => setTheme('dracula'),     when: theme !== 'dracula' },
    { id: 'thm.highcontrast', label: 'Theme: High contrast',         section: 'Theme', icon: '◐',
      run: () => setTheme('highcontrast'), when: theme !== 'highcontrast' },
    { id: 'thm.coffeeshop',  label: 'Theme: Coffee Shop',           section: 'Theme', icon: '☕',
      run: () => setTheme('coffeeshop'),  when: theme !== 'coffeeshop' },
    { id: 'thm.wallstreet',  label: 'Theme: Wolf of Wall Street',   section: 'Theme', icon: '📈',
      run: () => setTheme('wallstreet'),  when: theme !== 'wallstreet' },



    /* Workspaces. */
    ...workspaces.map(ws => ({
      id: 'ws.apply.' + ws.id,
      label: 'Workspace: ' + ws.name + (ws.id === activeWorkspace ? '  (active)' : ''),
      section: 'Workspaces',
      icon: ws.builtin ? '◇' : '◆',
      detail: ws.builtin ? 'built-in' : 'custom',
      run: () => onApplyWorkspace && onApplyWorkspace(ws),
    })),
    { id: 'ws.save', label: 'Save current state as workspace…', section: 'Workspaces', icon: '＋',
      run: () => onSaveWorkspace && onSaveWorkspace() },
    /* Show delete only when an active user-saved workspace exists. */
    ...(activeWorkspace
      ? workspaces.filter(w => w.id === activeWorkspace && !w.builtin).map(w => ({
          id: 'ws.del.' + w.id,
          label: 'Delete workspace "' + w.name + '"',
          section: 'Workspaces',
          icon: '✕',
          run: () => {
            if (window.confirm(`Delete workspace "${w.name}"?`) && onDeleteWorkspace) {
              onDeleteWorkspace(w.id);
            }
          },
        }))
      : []),

    /* Agents — one entry per hired agent so users can DM directly from the palette. */
    ...(agents || []).map(a => ({
      id: 'agent.dm.' + a.id,
      label: 'DM @' + a.name + (a.role ? '  · ' + a.role : ''),
      section: 'Agents',
      icon: a.elevated ? '🛡' : '👤',
      detail: a.status || 'idle',
      run: () => onDmAgent && onDmAgent(a),
    })),

    /* Recent chat (last 25 messages) — palette doubles as chat search. */
    ...((chat || []).slice(-25).reverse().map(m => ({
      id: 'chat.jump.' + m.id,
      label: (m.from === 'user' ? 'You: ' : (m.name || 'Agent') + ': ') + String(m.text || '').replace(/\s+/g, ' ').slice(0, 80),
      section: 'Recent chat',
      icon: m.from === 'user' ? '🅱' : '💬',
      run: () => onJumpToMessage && onJumpToMessage(m),
    }))),

    /* Comms — Phase 2 of the agent communication refactor. These commands
       surface the message registry through the palette so the boss can
       answer "what's happening?" without reaching for the inbox button.
       Counts are computed from the live messages list. */
    ...(() => {
      const list = Array.isArray(messages) ? messages : [];
      const active = list.filter(m => MSG_STATES[m.state] && !MSG_STATES[m.state].terminal).length;
      const blocked = list.filter(m => m.state === 'blocked').length;
      const failed = list.filter(m => m.state === 'failed').length;
      const cmds = [
        { id: 'comms.inbox', label: `Inbox · open${active ? ` (${active} active)` : ''}`,
          section: 'Comms', icon: '📬',
          run: () => onOpenInbox && onOpenInbox('active') },
      ];
      if (blocked > 0) cmds.push({
        id: 'comms.blockers', label: `Show blockers (${blocked})`,
        section: 'Comms', icon: '⚠',
        run: () => onOpenInbox && onOpenInbox('blocked')
      });
      if (failed > 0) cmds.push({
        id: 'comms.failed', label: `Show failed messages (${failed})`,
        section: 'Comms', icon: '✕',
        run: () => onOpenInbox && onOpenInbox('failed')
      });
      if (failed > 0 && onRetryFailed) cmds.push({
        id: 'comms.retry-failed', label: `Retry the most recent failed message`,
        section: 'Comms', icon: '↻', run: () => onRetryFailed()
      });
      return cmds;
    })(),

    /* /who-can — quick agent capability lookup. The label gets a sub-prompt
       when the user has typed something past 'who can'; otherwise it just
       opens a toast with the full capability roster. */
    { id: 'comms.who-can', label: '/who-can — find the right coworker for a job',
      section: 'Comms', icon: '🔎',
      run: () => {
        const q = window.prompt('Find coworkers who can do…\n(e.g. "code review", "docs", "deployment")', '');
        if (!q || !q.trim()) return;
        const hits = whoCan(agents, q);
        const toast = window.cafresohqToast;
        if (!hits.length) {
          toast && toast.warn(`No agent claims "${q}". (Hire one or set capabilities on an existing agent.)`);
          return;
        }
        const lines = hits.slice(0, 6).map(h =>
          `• ${h.agent.name} (${h.agent.role}): ${h.matches.join(', ')}`).join('\n');
        toast && toast.info(`Agents who can ${q}:\n${lines}`, { duration: 12000 });
      }
    },

    /* Help / discovery. */
    { id: 'help.shortcuts', label: 'Keyboard shortcuts', section: 'Help', icon: '⌨',
      run: () => window.cafresohqToast && window.cafresohqToast.info(
        'Cmd/Ctrl-K — palette · / — graph filter · Esc — close · ⌘P — graph palette',
        { duration: 8000 })
    },
    { id: 'help.tour', label: 'Replay onboarding tour', section: 'Help', icon: '🎓',
      run: () => window.dispatchEvent(new CustomEvent('cafresohq:replayTour'))
    },
  ];

  useCommands(cmds, [
    activeView, night, railCollapsed, chatWinOpen, anyBusy, density, theme,
    navigate, setNight, setRailCollapsed, setChatWinOpen, setDensity, setTheme,
    workspaces, activeWorkspace,
    onApplyWorkspace, onSaveWorkspace, onDeleteWorkspace,
    onHire, onSettings, onMissions, onWorkflow, onStandup, onMemory, onStopAll,
    agents, chat, onDmAgent, onJumpToMessage,
    onOpenInbox, onRetryFailed, messages,
  ]);

  return null;
}


export { AppGlobalCommands };
