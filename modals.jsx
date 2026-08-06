/* modals.jsx — barrel for the modal components (split into modals/).
   modals/providers.jsx (ApiTab / VaultTab / BraveTab and the CLI panels)
   is deliberately NOT imported: those tabs are kept for a future
   self-host build flag (see the note in HireModal) and shipping them
   in the managed build would just add dead weight. */
import { Modal } from './modals/base.jsx';
import { HireModal } from './modals/hire.jsx';
import { SettingsModal } from './modals/settings.jsx';
import { FurnishModal, InboxModal, MeetingRoomModal, WorkflowModal } from './modals/collab.jsx';
import { STARTER_TASKS, StarterCards, StarterTasksModal, buildStarterTask } from './modals/starter.jsx';
import { DeliverySheet } from './modals/delivery.jsx';

const CafresoHQModals = { Modal, HireModal, SettingsModal, WorkflowModal, MeetingRoomModal, InboxModal, FurnishModal,
  StarterTasksModal, StarterCards, STARTER_TASKS, buildStarterTask, DeliverySheet };

export { CafresoHQModals };
