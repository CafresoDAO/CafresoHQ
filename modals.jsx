/* modals.jsx — barrel for the modal components (split into modals/).

   This comment used to say `modals/providers.jsx` "is deliberately NOT
   imported", and it was read that way for a long time: #123 found a note
   in views/vault.jsx that had deleted a working control on the strength of
   it. It is not true, and has not been since #37/#39/#40/#60 rescued four
   of that file's panels — `modals/settings.jsx` imports VaultTab, MediaTab,
   BraveTab and BrowserKeysTab from it by name and renders them under
   Connections and Media. The barrel does not import providers.jsx because
   nothing here needs to, not because the file is held back from the build.

   What IS still unmounted is the rest of that file: `ApiTab` and the two
   CLI panels it renders (ClaudeCodePanel / CodexPanel) are not exported
   and not referenced outside their own definitions — the self-host setup
   surface, kept for a future build flag (see the note in HireModal). Said
   about those three, the original sentence would have been correct; said
   about the file, it outlived the fact by four tickets. */
import { Modal } from './modals/base.jsx';
import { HireModal } from './modals/hire.jsx';
import { SettingsModal } from './modals/settings.jsx';
import { FurnishModal, InboxModal, MeetingRoomModal, WorkflowModal } from './modals/collab.jsx';
import { STARTER_TASKS, StarterCards, StarterTasksModal, buildStarterTask, canSearchFor } from './modals/starter.jsx';
import { DeliverySheet } from './modals/delivery.jsx';

const CafresoHQModals = { Modal, HireModal, SettingsModal, WorkflowModal, MeetingRoomModal, InboxModal, FurnishModal,
  StarterTasksModal, StarterCards, STARTER_TASKS, buildStarterTask, canSearchFor, DeliverySheet };

export { CafresoHQModals };
