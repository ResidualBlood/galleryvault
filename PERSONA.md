# Target Personas

Who GalleryVault is built for. Every feature decision is weighed against these
two users — if it doesn't serve at least one of them, it doesn't ship.
(Still unvalidated against real users; updated as feedback arrives.)

## Persona A — "The Local Hoarder"（本地囤积者）

**Primary persona.** Self-hosted data hoarder who keeps an archive of
downloaded galleries and wants a proper library around them.

- **Background**: technical, 25–40, runs a NAS / home server, comfortable with
  Docker. Bilingual (reads English, prefers Chinese UI for tags).
- **Pain points today**
  - Ehviewer lives on the phone; on the PC the downloads are a mess of
    folders/archives with nothing to search.
  - Can't read/remember the English tag names; wants Chinese labels.
  - Downloads land randomly; no way to see what's already saved.
- **Job-to-be-done**: "Give me one self-hosted place where all my local
  galleries are searchable, readable, and tagged in Chinese — on any device."
- **What he values**: search & tag translation, the reader, non-intrusive
  downloads, backups, privacy (no cloud, no telemetry).
- **What he tolerates**: some initial setup effort (he's technical), a
  single-password instance, an early-stage UI.

**Success signal**: he can drop 20 GB of mixed Ehviewer/CBZ folders into the
library, find a specific artist in 3 seconds, and read it on his phone.

---

## Persona B — "The Completionist"（收藏整理控）

**Secondary persona.** An ExHentai power-user whose ten favorite folders are a
living archive they keep complete.

- **Background**: heavy ExHentai user, 10/10 favorite folders, hundreds of
  galleries, reads the metadata like a curator.
- **Pain points today**
  - Keeping the local copy in sync with favorites is manual and error-prone.
  - Duplicate versions (DL / uncensored / re-uploads) clutter the library.
  - Re-fetching metadata/tags for every new scan is slow.
- **Job-to-be-done**: "Keep my local library exactly in step with my favorites
  and tell me what's missing, without me doing the bookkeeping."
- **What he values**: favorites monitor & auto-download, duplicate scan,
  metadata cache (fast scans), Telegram notifications, exact sizes.

**Success signal**: favorites check runs on a schedule, downloads everything
new automatically, flags the duplicates, and the library stays metadata-fresh.

---

## Explicit non-targets

- Users who want a managed cloud service — GalleryVault is self-hosted only.
- Users who need per-account user management on day one (single password).
- Non-technical users on first setup — the
  [first-run wizard](ROADMAP.md) is the bridge we plan for them.
