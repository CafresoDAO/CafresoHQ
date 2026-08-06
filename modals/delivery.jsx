import { Sprite } from '../sprites.jsx';
import { Modal } from './base.jsx';
import { CafresoHQChain, CafresoHQClient } from '../claude-client.jsx';
const { useState } = React;

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
  /* Share state is keyed by path so a sheet for a NEW delivery never shows a
     previous one's link. Hook sits before the early return (hooks rule). */
  const [share, setShare] = useState(null);
  if (!open || !delivery) return null;
  const { path, agentId, agentName, agentColor, encrypted, taskTitle } = delivery;
  const isPage = /\.html?$/i.test(path || '');
  const shareFor = share && share.path === path ? share : null;
  /* Ship-to-chain (DRIVER_CONTRACT §7): only PAGES ship (a brief or a draft
     is a private note, not a site), and only when the II-holding shell is
     here to do real public hosting. No shell → no button, rather than a
     button that hands back a localhost link and calls it "shared". The
     user's click IS the approval — no extra stamp for a boss-initiated act. */
  const canShare = isPage && (() => {
    try { return !!(CafresoHQChain && CafresoHQChain.isAvailable && CafresoHQChain.isAvailable()); }
    catch (_e) { return false; }
  })();
  const doShare = async () => {
    setShare({ path, busy: true });
    try {
      const r = await CafresoHQClient.sharePage(path,
        agentId ? { tipJar: { agentId, agentName } } : {});
      setShare({ path, url: r.url });
    } catch (e) {
      setShare({ path, err: String(e && e.message || e).slice(0, 120) });
    }
  };
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
      {canShare && (
        <div className="delivery-share">
          {shareFor && shareFor.url ? (
            <div className="delivery-share-done">
              🚀 Live on the Internet Computer:{' '}
              <a href={shareFor.url} target="_blank" rel="noreferrer">{shareFor.url}</a>
            </div>
          ) : shareFor && shareFor.err ? (
            <div className="delivery-share-err">⚠ Didn't ship — {shareFor.err}</div>
          ) : (
            <>
              <button className="px-btn" style={{ fontSize: 'var(--text-10)' }}
                disabled={!!(shareFor && shareFor.busy)} onClick={doShare}>
                {shareFor && shareFor.busy ? 'Publishing…' : '🚀 Share it live'}
              </button>
              <span className="delivery-share-hint">
                Puts this page on the public internet at its own link — only if you say so.
              </span>
            </>
          )}
        </div>
      )}
      <p className="delivery-trust">
        {encrypted
          ? 'The cabinet is encrypted — only you can open it. Nothing in here leaves your control, including from us.'
          : 'The cabinet is your own vault folder on this machine. Nothing was uploaded anywhere; everything your team files stays where you can see it.'}
      </p>
    </Modal>
  );
}

export { DeliverySheet };
