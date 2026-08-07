/* ui.jsx — barrel for the shared UI components (split into ui/).
   Keeps the module name so the build entry and consumers stay unchanged. */
import { MobileTabBar, OfficeView, Rail, Tab, Ticker } from './ui/office.jsx';
import { AgentCards, ChatPanel } from './ui/chat.jsx';
import { Btn, Card, Checkbox, Field, Ico, NAV_ITEMS, SearchField, Select, Tabs, TextArea, TextField, Toggle, VocabCtx, getVocab } from './ui/primitives.jsx';
import { CommandPaletteProvider, PaletteFab, ToastProvider, useCommands, useToast } from './ui/feedback.jsx';
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
  PaletteFab,
  CEOPanel,
  InspectPanel,
  TokenHUD,
  TopbarMenu,
  ShortcutHud,
  Toast,
};

export { CafresoHQUI };
