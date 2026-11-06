# Commands

| Command | What it does |
| --- | --- |
| `/start` | Intro. `start=seal_STL-…` shows that seal's metadata. |
| `/help` | Command list and the limits. |
| `/seal` | Reply to a message or file to seal it. With no reply, the next message you send is sealed. In groups, a reply is the reliable path. |
| `/verify CODE` | Reply with the original, or send it next. |
| `/show CODE` | Metadata for a seal, commitment, or decision. Note text is not printed back. |
| `/witness CODE` | Witness, same rules as the button. |
| `/seals` | Recent seals in this chat. |
| `/audit` | Walk this chat's chain, commitments, decisions, and witness hashes. |
| `/commit [@name] [YYYY-MM-DD] title -- detail` | Propose. Reply to someone instead of `@name` if the username cannot be resolved. No counterparty means a promise to yourself. |
| `/commitments` | Your commitments in this chat. |
| `/fulfill CODE` | Mark an active commitment fulfilled. |
| `/cancel` | Clear a pending seal or verify. |
| `/cancel CODE` | Cancel an open commitment you are party to. |
| `/decide question` | Open a yes/no/abstain decision and seal the question. |
| `/decisions` | Decisions in this chat. |
| `/close CODE` | Seal the tally. Opener, owner, or chat admin. |
| `/export` | JSON document of your records. |
| `/forget` | Asks for a button, then deletes stored copies of your notes. |
| `/settings` | Shows plan, quota, retention, username display. |
| `/settings retain on\|off` | Whether future notes keep a private copy. Default off. |
| `/settings username on\|off` | Whether your `@username` appears on witness lines. |
| `/quota` | Same snapshot as settings. |
| `/health` | Owner only. Integrity, counts, version. No token. |
| `/grant USER_ID [free\|pro]` | Owner only. Defaults to pro. |
| `/revoke USER_ID` | Owner only. Sets free. |

Buttons: Witness, Accept, Decline, Fulfilled, Cancel, Yes, No, Abstain, Close and seal, Delete my note copies.

Inline mode: an empty query returns a short explanation. A known code returns the same metadata card. An unknown code returns no result.

Unknown commands get a one-line pointer to `/help`. Ordinary group chatter is ignored.
