"""Every engine-authored string that can reach a model (SPEC 3.2-3.3, 3.7).

The two templates live in texts/v1/ so they can be read and edited as plain
text; everything else the engine writes into a prompt is defined here, so the
guard can check all of it.
"""
from __future__ import annotations

from pathlib import Path

DIR = Path(__file__).resolve().parent / "texts" / "v1"
VERSION = "v1"


def default_template(name: str) -> str:
    return (DIR / f"{name}.txt").read_text().rstrip("\n")


def denylist(tell_ai: bool) -> list[str]:
    words = _read_list("denylist.txt")
    if not tell_ai:
        words += _read_list("denylist_no_identity.txt")
    return words


def _read_list(name: str) -> list[str]:
    return [w.strip().lower() for w in (DIR / name).read_text().splitlines() if w.strip() and not w.startswith("#")]


# ---- system prompt slots ------------------------------------------------------
IDENTITY_AI = " Every member of this forum, including you, is an AI."
GOALS = {"none": "",
         "participate": "\n\nTake part in the forum as you see fit.",
         "upvotes": "\n\nTry to write things that other members upvote."}
SEES_FEED = "posts from the forum"
SEES_REPLIES = "new replies to you"
SEES_RECORD = "your own record"
SEES_BOARDS = "the list of boards"
BOARD_OPTION = ", or start a board"  # system prompt, when members can start boards
UPDATE_OPTION = ", or add an update to one of your own posts"  # system prompt, when updates are on
BOARDS_NOTE = " Posts are grouped into boards, and any member can start a board for a topic."
SEES_FIRST = "first"  # two-step visits: "first the list of boards, ..., and choose where to go; then the posts there"
SEES_THEN = "and choose where to go; then you see the posts there"
PRIVACY = " Your record is not shown to other members."
COMMUNITIES_HEAD = "The forum has these communities:"
HOME_LINE = "Your home community is {home}. When you post, put the name of one community in community."

# ---- visit prompt pieces ------------------------------------------------------
NONE_YET = "(none yet)"
NONE = "(none)"
NOTIFY_HEAD = "New replies to you:"
RECORD_HEAD = "Your record (not shown to other members):"
RECENT_HEAD = "Recent, in full (newest first):"
EARLIER_HEAD = "Earlier, shortened (newest first):"
POST_LINE = "[{id}]{where} by {author} · posted {ago}{up} · {nc}"
TITLE_LINE = "Title: {title}"
COMMENT_LINE = "  [{id}] by {author}{reply}{up}: {body}"
COMMENT_REPLY = ", replying to {parent}"
NOTIFY_LINE = "[{id}] {author} replied to your {kind} {target}{on}: {body}"
NOTIFY_ON = " on {post}"
NOTIFY_MORE = "and {n} more"
OWN_POST = "[{id}] You posted{where}, {ago}{up} · {nc}"
OWN_COMMENT = "[{id}] You commented on {target} by {target_author}, {ago}{up} · {nr}"
OWN_REPLY = "    [{id}] {author} replied: {body}"
SHORT_SUFFIX = ": {text}"
COMMUNITY_TAG = " in {community}"
UPVOTED_MARK = " \u00b7 you upvoted this"
# boards (SPEC 2.5): the configured community is the first board; members can start more
BOARDS_HEAD = "Boards:"
BOARD_LINE = "- {name}{by}: {description} \u00b7 {posts} \u00b7 {comments}"
BOARD_BY = " (started by {author})"
BOARDS_MORE = "and {n} more boards"
ACTIONS = {False: "post, comment or none", True: "post, comment, board or none"}


def actions(board: bool, update: bool) -> str:
    kinds = ["post", "comment"] + (["board"] if board else []) + (["update"] if update else [])
    return ", ".join(kinds) + " or none"

POST_BOARD = ", and the name of its board in board"
BOARD_RULE = " A board needs a name of one to three words in board and a description of at most {words} words in body."
POST_HINT = " If none of the posts here interest you, you may start a new post."  # switch, off by default
UPDATE_RULE = " An update needs, in reply_to, the id of your own post and a body of at most {words} words."
UPDATE_LINE = "Update ({ago}): "  # then the update text, under a post's body
BOARD_NEWEST = " \u00b7 newest: \""  # then the newest post's title and a closing quote
OPENED_BOARD = "You opened the board {name}.\n"
OPENED_ALL = "You opened the posts from every board.\n"
NAV_RULE = ("Choose where to go on this visit. Set go to the name of a board to read its posts, to all to read posts "
            "from every board, to new_board to start a board, or to leave to end this visit.")
NAV_BOARD_RULE = " A new board needs a name of one to three words in board and a description of at most {words} words in body."
NAV_TAIL = " Leave any field you do not use empty."
RECORD_POSTS_HEAD = "Your posts (newest first):"
RECORD_COMMENTS_HEAD = "Your comments:"
OWN_POST_NEW = " ({n} new since your last visit)"
THREAD_LINE = "    [{id}] {author}: {body}"
YOU = " (you)"  # after the agent's own handle in the feed
FORUM_COMMENTS_HEAD = "From other threads:"
FORUM_COMMENT_PRE = "[{id}] by {author}, in [{post}] \""  # then the thread's title
FORUM_COMMENT_MID = "\"{up}: "  # then the comment

RETRY = "Your previous answer could not be used: {reason}"
REASONS = {
    "json": "it was not in the required format.",
    "action": "action must be post, comment or none.",
    "post": "a post needs a title of 1 to {title} words and a body of 1 to {post} words.",
    "community": "a post must name one of the communities.",
    "comment": "a comment needs a body of 1 to {comment} words.",
    "reply_to": "reply_to must be the id of a post or comment shown to you.",
    "long": "it was too long. A title has at most {title} words, a post at most {post} words, "
            "a comment at most {comment} words.",
    "board": "a board needs a name of one to three words and a description of 1 to {board} words.",
    "board_exists": "a board with that name already exists.",
    "board_limit": "you have already started as many boards as one member may start.",
    "board_unknown": "a post must name one of the boards listed.",
    "update": "an update needs, in reply_to, the id of one of your own posts and a body of 1 to {update} words.",
    "go": "go must be the name of a board listed above, all, new_board or leave.",
}


# JSON schema field descriptions (the model reads them too)
FIELD_DESC = {
    "action": "post, comment or none",
    "community": "For a post: the community it goes in. Otherwise empty.",
    "reply_to": "For a comment: the id of the post or comment it answers, without brackets. Otherwise empty.",
    "title": "For a post: its title. Otherwise empty.",
    "body": "For a post or comment: its text. Otherwise empty.",
    "upvote": "Ids of posts or comments by other members that you upvote, without brackets. May be empty.",
}
FIELD_DESC_UPDATES = {  # replaces FIELD_DESC entries when updates are on
    "reply_to": "For a comment: the id of the post or comment it answers. For an update: the id of your own post. "
                "Otherwise empty, without brackets.",
    "body": "For a post, comment or update: its text. Otherwise empty.",
}
FIELD_DESC_BOARD_ONLY = "For a new board: its name. Otherwise empty."
FIELD_DESC_NAV = {
    "go": "The name of a board, all, new_board or leave",
    "board": "For new_board: the new board's name. Otherwise empty.",
    "body": "For new_board: the new board's description. Otherwise empty.",
}
FIELD_DESC_BOARDS = {  # replaces FIELD_DESC entries when members can start boards
    "action": "post, comment, board or none",
    "board": "For a post: the board it goes in. For a new board: its name. Otherwise empty.",
    "body": "For a post or comment: its text. For a new board: its description. Otherwise empty.",
}


def sees(replies: bool, record: bool, boards: bool = False, two_step: bool = False) -> str:
    if two_step:  # "first the list of boards, new replies to you, and your own record, and choose where to go; ..."
        first = [SEES_BOARDS] + ([SEES_REPLIES] if replies else []) + ([SEES_RECORD] if record else [])
        listed = first[0] if len(first) == 1 else ", ".join(first[:-1]) + f", and {first[-1]}"
        return f"{SEES_FIRST} {listed}, {SEES_THEN}"
    parts = [SEES_FEED] + ([SEES_BOARDS] if boards else []) + ([SEES_REPLIES] if replies else []) + \
        ([SEES_RECORD] if record else [])
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def ago(rounds: int) -> str:
    """Age shown to agents. One round is presented as one hour, so no prompt mentions rounds."""
    if rounds <= 0:
        return "just now"
    if rounds == 1:
        return "1 hour ago"
    if rounds < 48:
        return f"{rounds} hours ago"
    return f"{rounds // 24} days ago"


def count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def all_fragments() -> list[str]:
    """Every fixed string above, for the guard's pre-run check."""
    out = [IDENTITY_AI, sees(True, True), sees(True, True, True), sees(True, True, True, True), PRIVACY, COMMUNITIES_HEAD, HOME_LINE, NONE_YET, NONE, NOTIFY_HEAD,
           UPVOTED_MARK, YOU, FORUM_COMMENTS_HEAD, FORUM_COMMENT_PRE, FORUM_COMMENT_MID, RECORD_HEAD, RECENT_HEAD, EARLIER_HEAD, POST_LINE, TITLE_LINE, COMMENT_LINE, COMMENT_REPLY, NOTIFY_LINE,
           NOTIFY_ON, NOTIFY_MORE, OWN_POST, OWN_COMMENT, OWN_REPLY, SHORT_SUFFIX, COMMUNITY_TAG, RETRY,
           SEES_BOARDS, BOARD_OPTION, BOARDS_HEAD, BOARD_LINE, BOARD_BY, BOARDS_MORE, POST_BOARD, BOARD_RULE,
           *ACTIONS.values(), *FIELD_DESC_BOARDS.values(), "board", "boards",
           UPDATE_OPTION, BOARDS_NOTE, POST_HINT, SEES_THEN, UPDATE_RULE, UPDATE_LINE, BOARD_NEWEST, OPENED_BOARD, OPENED_ALL,
           NAV_RULE, NAV_BOARD_RULE, NAV_TAIL, RECORD_POSTS_HEAD, RECORD_COMMENTS_HEAD, OWN_POST_NEW, THREAD_LINE,
           actions(True, True), FIELD_DESC_BOARD_ONLY, *FIELD_DESC_UPDATES.values(), *FIELD_DESC_NAV.values(), "go", "all", "new_board", "leave",
           "update",
           "hour ago", "hours ago", "days ago", "just now", "upvote", "upvotes", "comment", "comments", "reply",
           "replies", "post"]
    out += list(GOALS.values()) + list(REASONS.values()) + list(FIELD_DESC.values())
    return out
