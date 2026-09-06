import { MSG_STATES } from './windows.jsx';
import { whoCan, whoCanLine } from './agents.jsx';
import { grantedTools } from './cast.jsx';
import { HQ } from '../hq-runtime.jsx';
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
  /* Is the floating chat window actually MOUNTED? app.jsx gates it behind
     `!isNarrowViewport`, so on a phone `chatWinOpen` is a flag nothing
     renders. Defaults true so an omitted prop can't hide the close verb on
     a desktop. */
  chatWindowMounted = true,
  density, setDensity,
  theme, setTheme,
  windowsEnabled, setWindowsEnabled, onOpenWindow,
  workspaces = [], activeWorkspace, onApplyWorkspace, onSaveWorkspace, onDeleteWorkspace,
  onHire, onSettings, onMissions, onWorkflow, onStandup, onMemory, onStopAll,
  onShortcuts,
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
    { id: 'nav.vault',      label: 'Switch view: Library',     section: 'Navigation', icon: '📓', run: () => navigate('vault') },
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
      /* 'Projects', matching nav.projects thirty lines above — this file
         had both names for the same id. See NAV_ITEMS for why Projects
         won. */
      ['vault','Library'],['projects','Projects'],['terminal','Terminal'],
    ].map(([v, lbl]) => ({
      id: 'win.open.' + v, label: 'Open in window: ' + lbl, section: 'Windows', icon: '🪟',
      run: () => onOpenWindow(v),
    })) : []),
    /* `navigate('chat')` to OPEN — not the raw setter. The floating chat
       window is mounted only on wide viewports (app.jsx gates it behind
       `!isNarrowViewport`), so on a phone `setChatWinOpen(v => !v)` flips a
       flag nothing renders: the exact silent no-op the RAIL was moved off
       this same setter to avoid ("navTo, not setChatWinOpen — it already
       routes chat correctly in BOTH modes").

       And `chatWinOpen` is persisted and defaults to TRUE, so on a phone
       this entry usually read "Close chat window" — over a chat that was
       not on screen, offering the boss no way to open one. Closing still
       uses the setter, but only where the window it closes exists. */
    { id: 'tog.chat',
      label: (chatWindowMounted && chatWinOpen) ? 'Close chat window' : 'Open chat',
      section: 'Toggles', icon: '💬',
      run: () => ((chatWindowMounted && chatWinOpen)
        ? setChatWinOpen(false)
        : navigate('chat')),
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
          run: async () => {
            if ((await window.hqConfirm(`Delete workspace "${w.name}"?`, { danger: true })) && onDeleteWorkspace) {
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
      label: (m.from === 'user' ? 'You: ' : (m.name || 'A coworker') + ': ') + String(m.text || '').replace(/\s+/g, ' ').slice(0, 80),
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
       opens a toast with the full capability roster.

       The skill words are a guess off the job title; the reach beside them
       is not. `grantedTools(tools, capabilityFacts(agent))` is the product's
       single answer to "what can this coworker actually reach" — the same
       pair the coworker card, the inspect panel and the candidate shelf
       ask — and passing it in is what stops this list from rating a
       coworker with nothing ticked exactly like one holding the tool. */
    { id: 'comms.who-can', label: '/who-can — find the right coworker for a job',
      section: 'Comms', icon: '🔎',
      run: async () => {
        const q = await window.hqPrompt('Find coworkers who can do…\n(e.g. "code review", "docs", "deployment")', { value: '' });
        if (!q || !q.trim()) return;
        const hits = whoCan(agents, q, a => grantedTools(a.tools, HQ.capabilityFacts(a)));
        const toast = window.cafresohqToast;
        if (!hits.length) {
          /* This used to end "(Hire one or set capabilities on an existing
             agent.)" — and `capabilities` is a field nothing in the product
             writes. Of the two ways out it offered, one was a control that
             does not exist. Job titles are the real input here and they are
             a select at hire with no later edit, so the honest routes are a
             new hire or asking whoever is nearest. */
          toast && toast.warn(
            `No coworker's job title covers "${q}". Titles are set when you hire and can't be changed after — `
            + `hire someone from the front desk, or @-mention whoever is closest and say what you need.`,
            { duration: 12000 });
          return;
        }
        const lines = hits.slice(0, 6).map(whoCanLine).join('\n');
        toast && toast.info(`Agents who can ${q}:\n${lines}`, { duration: 12000 });
      }
    },

    /* Help / discovery.

       This used to pop its own toast listing four shortcuts, two of which
       — "/ — graph filter" and "⌘P — graph palette" — never existed
       anywhere in the app (no keydown listener in views/graph.jsx at all;
       the real global `/` handler in app.jsx focuses the chat composer,
       not any graph filter; no 'p'/'P' key handler exists anywhere in the
       repo). That toast was a second, hand-maintained shortcuts list that
       drifted the moment the real one changed — ShortcutHud (ui/panels.jsx,
       opened by the real ⌘K handler this entry's own hint names) is the
       one place that list is actually kept in sync with app.jsx's key
       handlers. Opening it instead of a separate toast means there is only
       one shortcuts list left to go stale. */
    { id: 'help.shortcuts', label: 'Keyboard shortcuts', section: 'Help', icon: '⌨',
      run: () => onShortcuts && onShortcuts()
    },
    { id: 'help.tour', label: 'Replay onboarding tour', section: 'Help', icon: '🎓',
      run: () => window.dispatchEvent(new CustomEvent('cafresohq:replayTour'))
    },
    /* The door back from the checklist's ✕ (`## 412.`) — see the `showGettingStarted`
       listener in app.jsx for what that click actually took away. The tour
       above is NOT that door: it opens a different surface, and the
       checklist's render guard hides the card for as long as the tour is up.
       Listed unconditionally, like the tour, because the palette cannot see
       `gsDismissed` and a command that appears only once you already know
       to look for it is not a way back. */
    { id: 'help.gettingstarted', label: 'Show getting started checklist', section: 'Help', icon: '✦',
      run: () => window.dispatchEvent(new CustomEvent('cafresohq:showGettingStarted'))
    },
  ];

  useCommands(cmds, [
    activeView, night, railCollapsed, chatWinOpen, chatWindowMounted, anyBusy, density, theme,
    navigate, setNight, setRailCollapsed, setChatWinOpen, setDensity, setTheme,
    windowsEnabled, setWindowsEnabled, onOpenWindow,
    workspaces, activeWorkspace,
    onApplyWorkspace, onSaveWorkspace, onDeleteWorkspace,
    onHire, onSettings, onMissions, onWorkflow, onStandup, onMemory, onStopAll,
    onShortcuts,
    agents, chat, onDmAgent, onJumpToMessage,
    onOpenInbox, onRetryFailed, messages,
  ]);

  return null;
}


export { AppGlobalCommands };
