/* ui.jsx — barrel for the shared UI components (split into ui/).
   Keeps the module name so the build entry and consumers stay unchanged. */
import { MobileTabBar, OfficeView, Rail, Tab, Ticker } from './ui/office.jsx';
import { AgentCards, ChatPanel } from './ui/chat.jsx';
import { Btn, Card, Checkbox, Field, Ico, NAV_ITEMS, SearchField, Select, Tabs, TextArea, TextField, Toggle, VocabCtx, getVocab } from './ui/primitives.jsx';
import { CommandPaletteProvider, ToastProvider, useCommands, useToast } from './ui/feedback.jsx';
import { GettingStarted, NotificationBell, NotificationCenter, OnboardingKeyStep, OnboardingTour } from './ui/onboarding.jsx';
import { CEOPanel, InspectPanel, ShortcutHud, Toast, TokenHUD, TopbarMenu } from './ui/panels.jsx';

const CafresoHQUI = {
  Rail,
  MobileTabBar,
  OfficeView,
  Ticker,
  ChatPanel,
  AgentCards,
  Ico,
  NAV_ITEMS,
  Btn,
  Card,
  Field,
  TextField,
  TextArea,
  Select,
  Checkbox,
  Toggle,
  SearchField,
  Tabs,
  Tab,
  ToastProvider,
  useToast,
  CommandPaletteProvider,
  useCommands,
  NotificationBell,
  NotificationCenter,
  OnboardingTour,
  OnboardingKeyStep,
  GettingStarted,
  VocabCtx,
  getVocab,
  CEOPanel,
  InspectPanel,
  TokenHUD,
  TopbarMenu,
  ShortcutHud,
  Toast,
};

export { CafresoHQUI };

// ── Glass-Box Telemetry Bar ──────────────────────────────────────────────────
export function TelemetryBar({ message, isIdle = false }) {
  const { useState, useEffect } = React;
  const [visibleMsg, setVisibleMsg] = useState(message);
  const [active, setActive] = useState(false);

  useEffect(() => {
    if (message && !isIdle) {
      setVisibleMsg(message);
      setActive(true);
    } else if (isIdle && active) {
      // Show idle briefly then fade out
      setVisibleMsg("✅ Agent Idle");
      const t = setTimeout(() => setActive(false), 1500);
      return () => clearTimeout(t);
    } else if (!message) {
      setActive(false);
    }
  }, [message, isIdle]);

  if (!visibleMsg) return null;

  return (
    <div className="telemetry-container">
      <div className={`telemetry-bar ${active ? 'active' : ''}`}>
        {!isIdle && active && <div className="spinner" />}
        <span>{visibleMsg}</span>
      </div>
    </div>
  );
}
