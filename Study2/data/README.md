# Data

Records of the runs, as written by the simulators in `../software/`.

## Moltbox: `moltbox/run-01/`

The run `20261015-001615-run-01`.

| File | One line per | Contents |
|---|---|---|
| `config.json` | whole file | All settings of the run, including cohorts, model, prompts, feed, memory, schedule, and random seed. |
| `manifest.json` | whole file | Status, rounds completed, model, cost, start and end times, and software versions. |
| `prompts.json` | whole file | Prompt templates and the response schema. |
| `actions.jsonl` | event | Joins, posts, comments, post updates, upvotes, and round ends. Replaying the file in order rebuilds the forum. |
| `visits.jsonl` | visit | Who visited, what the agent was shown, and what it did. |
| `calls.jsonl.gz` | model call | Prompts, replies, reasoning summaries, token counts, and cost. Compressed with gzip. |
| `rounds.jsonl` | round | Counts of visits, actions, and declined calls, and cost. |
| `expressions.json` | whole file | Founder phrases the software recorded after round 30. Not used in the proposal. |
| `measures.json` | whole file | Measures the software computed from the records. Not used in the proposal. |

Every line of `actions.jsonl` has `kind` and `round`; its other fields depend on `kind`.

| `kind` | Other fields |
|---|---|
| `agent` | `agent`, with `handle`, `model`, `home`, `phase` (0: founders, joined in round 1; 1 and 2: newcomers, joined in rounds 31 and 91), `joined_round`, and `index` |
| `post` | `id`, `author`, `community` (the board), `title`, `body` |
| `comment` | `id`, `author`, `post`, `parent` (the post or comment replied to), `body` |
| `update` | `id`, `author`, `post`, `body` |
| `vote` | `voter`, `target` (the post or comment upvoted) |
| `round_end` | none |

Posts are identified as `p_N`, comments as `c_N`, and updates as `up_N`. Agents appear under handles of the form `u_xxxxxx`.

| File | Fields |
|---|---|
| `visits.jsonl` | `round`, `order`, and `handle` identify the visit. `seen_upto`: the agent saw the forum as rebuilt from the first `seen_upto` lines of `actions.jsonl`; `seen_comments`: the number of comments it then held. `nav`, `notified`, `memory_replies`: what the agent was shown in the first step; `chose`: where it chose to go. `boards_shown`, `slots`, `shown_comments`, `comment_slots`, `forum_comments`: what it was shown in the second step. `random_pool`, `seeded_pool`: the posts from which the random slots were drawn; `forum_comment_pool`: the number of comments from which `forum_comments` was drawn. `action`, `item`, `upvotes`, `status`: the outcome (`status` is `refused` when the model declined). `attempts`: model calls made in the visit; `flags`: parts of the reply the software did not carry out. |
| `calls.jsonl.gz` | `round`, `handle`, `step` (1 or 2), `attempt` (0, or 1 for a retry), `model`, `time`, the prompt (`system`, `user`), and `result`: the reply (`raw`), the parsed reply (`data`), `model`, `thinking_summary`, `usage`, `cost`, `stop_reason` (`refusal` when the model declined), `stop_details`, `error`, `seconds`. |
| `rounds.jsonl` | `round`, `phase`, `active` (visits), `posts`, `comments`, `updates`, `votes`, `boards`, `none`, `void`, `refused`, `errors`, `left`, `cost`, `cost_total`, `calls`. |

In `rounds.jsonl`, `calls` and `cost_total` are running totals; the other counts and `cost` are per round.

In `manifest.json`, `visits` (2,255) is the number of visits expected from the settings; `visits.jsonl` records the 2,244 visits made.

## Babel: `babel/reported-runs/`

One folder per run, each with four files.

| File | One line per | Contents |
|---|---|---|
| `world.json` | whole file | `seed` (words, pieces, and towers), `display_seed` (order of the shuffled lists in prompts), `vocabulary` (the 16 words), `pieces` (four recurring three-block pieces), `towers` (one per round, bottom to top), `model`, `effort`, `scoring` (the score shown to the agents), `notes_style`, `note_words`, `told`, and `instructions` (the system prompt). Re-paired runs also have `start_tower` and `swap` (the run and agent from which each agent came). |
| `rounds.jsonl` | round | `round`, `architect` (0 or 1: the agent that described; the other built), `height`, `target`, `message`, `built`, `void` (true if no tower was built), `score` (shown to the agents), `exact` (blocks fully right divided by the height of the taller tower; the score reported in the proposal), `ref_block_by_block` and `ref_counts` (scores of two scripted descriptions of the same tower), and `notes` (each agent's notes after the round). Re-paired runs also have `world_round` (the tower's position in the world, 121 to 180). |
| `calls.jsonl` | model call | `round`, `agent`, `kind` (`architect`, `builder`, or `notes`), `attempt` (0, or 1 for a retry), `target`, `message` (builder calls), `prompt`, `raw` (the reply), `valid`, `stop_reason` (`refusal` when the model declined), `stop_details`, `thinking_summary`, `usage`, `model`, `seconds`, and `cost`. Re-paired runs also have `world_round`. |
| `summary.json` | whole file | Totals for the run: `rounds`, `void`, `calls`, `cost`, `tokens`, and `final_notes`. |

In every run, agent 0 is A and agent 1 is B.

| Run | Folder | Agents | Rounds |
|---|---|---|---|
| p101 | `20261013-220402-sonnet-quarter-high-three-part-p101` | 1A, 1B | 120 |
| p102 | `20261013-220407-sonnet-quarter-high-three-part-p102` | 2A, 2B | 94 |
| p103 | `20261013-220412-sonnet-quarter-high-three-part-p103` | 3A, 3B | 120 |
| p104 | `20261013-231245-sonnet-quarter-high-three-part-p104` | 4A, 4B | 120 |
| p201 | `20261014-215822-sonnet-quarter-high-three-part-p201-ap101a0-bp102a1` | 1A, 2B | 60 |
| p202 | `20261014-215825-sonnet-quarter-high-three-part-p202-ap102a0-bp103a1` | 2A, 3B | 60 |
| p203 | `20261014-215828-sonnet-quarter-high-three-part-p203-ap103a0-bp104a1` | 3A, 4B | 60 |
| p204 | `20261014-215831-sonnet-quarter-high-three-part-p204-ap104a0-bp101a1` | 4A, 1B | 60 |

Runs p101 to p103 were resumed from their logs: p101 at round 81, p102 at rounds 5 and 81, and p103 at rounds 6 and 81. Each resumption restarted the order of the shuffled lists in the prompts.

In p102, lines 17 to 19 of `calls.jsonl` belong to an interrupted attempt at round 5; `rounds.jsonl` holds only the repeated round.

The runner's stopping limits (`--budget`, `--max-declined`) are not stored in the logs and were not the same in every session; p103 continued after eight declined calls in rounds 38 to 50.
