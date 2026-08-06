import { Sprite } from '../sprites.jsx';
import { Modal } from './base.jsx';

/* ── <DeliverySheet> — first-delivery beat (OFFICE_AS_INTERFACE §3 step 6) ──
   Shown ONCE, the first time a coworker's work lands in the cabinet. This is
   the payoff of the whole first run: a real file, in a real place, that the
   user can open.

   The trust line is conditional on purpose. "The cabinet is encrypted — only
   you can open it" is true only when this HQ is framed by the shell that
   holds the user's identity and does the vetKeys work; a self-hosted vault is
   an ordinary folder. Claiming encryption there would be exactly the kind of
   dishonesty §4 forbids of the animation layer, and it would be a lie about
   security, which is the worst kind to tell. So we say which one it is. */
function DeliverySheet({ open, delivery, onClose, onOpenNote }) {
  if (!open || !delivery) return null;
  const { path, agentName, agentColor, encrypted, taskTitle } = delivery;
  const isPage = /\.html?$/i.test(path || '');
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="FIRST DELIVERY"
      subtitle="filed to your cabinet"
      size="sm"
      footer={
        <>
          <button className="px-btn ghost" style={{ fontSize: 'var(--text-10)' }} onClick={onClose}>
            Later
          </button>
          <button className="px-btn primary" style={{ fontSize: 'var(--text-10)' }}
            onClick={() => { onOpenNote(path); onClose(); }}>
            {isPage ? 'Open the page →' : 'Open it →'}
          </button>
        </>
      }
    >
      <div className="delivery-head">
        <Sprite data={agentColor} scale={3} />
        <div className="delivery-note">
          <strong>{agentName}</strong> finished <em>{taskTitle}</em> and filed it
          in your cabinet.
        </div>
      </div>
      <div className="delivery-path" title={path}>📁 {path}</div>
      <p className="delivery-trust">
        {encrypted
          ? 'The cabinet is encrypted — only you can open it. Nothing in here leaves your control, including from us.'
          : 'The cabinet is your own vault folder on this machine. Nothing was uploaded anywhere; everything your team files stays where you can see it.'}
      </p>
    </Modal>
  );
}

export { DeliverySheet };
