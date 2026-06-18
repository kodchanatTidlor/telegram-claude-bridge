"""Group/topics mode — additive layer on top of DM mode.

Enabled when cfg.group_id is set. Messages then go to the supergroup, one
forum topic per project (cwd). DM mode (group_id == 0) is untouched.
"""


def is_group_mode(cfg) -> bool:
    return bool(cfg.group_id)


def target_chat(cfg) -> int:
    """Where outbound messages go: the group in group mode, else the DM."""
    return cfg.group_id if cfg.group_id else cfg.allowed_chat_id


def is_allowed_group(cfg, chat_id, user_id) -> bool:
    """Group mode auth: the message must be in our group AND from the owner —
    so other members can't drive Claude."""
    return chat_id == cfg.group_id and user_id == cfg.allowed_chat_id


def _base(cwd) -> str:
    return (cwd or "").rstrip("/").rsplit("/", 1)[-1] or (cwd or "?")


def resolve_topic(store, sid, cwd, live_sids, create_fn):
    """Return the forum topic id for a session, creating one if needed.

    - Already bound → return it.
    - A topic for this cwd exists and is FREE (its session no longer live) →
      reuse (rebind to this session, drop the stale binding).
    - Else create a new topic named after the cwd basename, suffixing ``#N``
      if a LIVE topic already uses that basename.
    """
    existing = store.topic_of(sid)
    if existing is not None:
        return existing

    topics = store.topics()
    live = set(live_sids)
    for osid, e in topics.items():
        if e.get("cwd") == cwd and osid not in live:
            store.drop_topic(osid)
            store.set_topic(sid, e["topic_id"], cwd)
            return e["topic_id"]

    base = _base(cwd)
    live_names = {_base(e.get("cwd")) for osid, e in topics.items()
                  if osid in live}
    name, n = base, 2
    while name in live_names:
        name, n = f"{base} #{n}", n + 1
    topic_id = create_fn(name)
    store.set_topic(sid, topic_id, cwd)
    return topic_id


def session_of_topic(store, topic_id):
    """Inbound: which session owns this topic (for routing a reply)."""
    for sid, e in store.topics().items():
        if e.get("topic_id") == topic_id:
            return sid
    return None
