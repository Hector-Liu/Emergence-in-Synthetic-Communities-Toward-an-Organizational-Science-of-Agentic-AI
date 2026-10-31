"use strict";
// Language switch for the page. Chinese is the source language: strings in app.js and
// index.html are written in Chinese and EN maps them to English. t() handles everything the
// script renders; translateStatic() handles the fixed HTML (text, placeholder, aria-label, title).
const I18N = (() => {
  const EN = {
    // shell
    "AI Agent 论坛模拟": "AI agent forum simulation", "实验": "Study", "管理": "Admin", "设计": "Design", "运行": "Run", "论坛": "Forum",
    "结果": "Results", "记录": "Runs", "模型与密钥": "Models & key", "当前运行": "Current run", "选择当前运行": "Choose the current run",
    "还没有运行": "No runs yet", "(还没有运行)": "(no runs yet)", "外观": "Appearance", "浅色": "Light", "深色": "Dark", "跟随系统": "System",
    "密钥已设置": "Key set", "未设置密钥": "No API key", "语言": "Language",
    "设定流程、Agent 和提示词,然后按步骤开始": "Set the phases, agents and prompts, then follow the steps",
    "当前运行的实时进度": "Live progress of the current run",
    "像读论坛一样读这次运行;点编码看它的主页,以及它每一次访问时看到的论坛": "Read the run like a forum; click a handle for its profile and the forum as it saw it at each visit",
    "主要分析与描述性指标(由程序计算,不用模型打分)": "Primary analysis and descriptive measures (computed by program, no model grading)",
    "所有运行;点一行设为当前运行": "All runs; click a row to make it the current run", "API 密钥和价格": "API key and prices",
    // statuses and kinds
    "完成": "Done", "运行中": "Running", "已停止": "Stopped", "预算停": "Budget stop", "规则停": "Rule stop", "中断": "Interrupted",
    "出错": "Error", "词检拦截": "Blocked by word check", "准备中": "Starting", "冒烟": "Smoke", "先验独白": "Prior (solo)", "模拟": "Mock", "正式": "Main",
    "创始": "Founder", "新成员": "Newcomer",
    // design: flow
    "流程": "Phases", "每一行是一个阶段:这一阶段新加入多少个 Agent、用什么模型、跑多少轮。轮数跨阶段连续计数。":
      "Each row is a phase: how many agents join, which model they use, and how many rounds it runs. Rounds are numbered across phases.",
    "阶段名": "Phase", "新加入": "Join", "模型": "Model", "轮数": "Rounds", "轮次": "Range", "选择轮次": "Choose round", "在场": "Present", "操作": "Actions",
    "添加阶段": "Add phase", "最后阶段加一组(混合模型)": "Add a group to the last phase (mixed models)",
    "在最后一个阶段里加一组用别的模型的 Agent": "Add agents with another model to the last phase", "恢复默认": "Reset to default",
    "运行名称": "Run name", "例如 pilot-1": "e.g. pilot-1", "随机种子 seed": "Random seed", "决定编码、分组和随机抽帖": "Sets handles, groups and random feed draws",
    "预算上限 (USD)": "Budget cap (USD)", "快到上限自动停,可加预算后继续": "Stops before the cap; raise it and resume",
    "同一阶段 · 另一组": "Same phase · another group", "删除阶段 {n}": "Delete phase {n}", "删除这一组": "Delete this group",
    "{p} 个阶段 · {a} 个 Agent · {r} 轮 · {m}": "{p} phases · {a} agents · {r} rounds · {m}",
    // design: agents
    "Agent 设定": "Agents", "告诉 Agent 成员都是 AI": "Tell agents all members are AI", "关掉后,任何提示词都不提 AI 或人": "When off, no prompt mentions AI or humans",
    "私有记忆": "Private memory", "自己的全部发言、得赞数、收到的回复": "Own posts and comments, their upvotes, replies received",
    "独白(solo)": "Solo", "看不到任何别人的内容。用来做「先验语料」": "Sees no one else's content. Used as the prior corpus",
    "目标句": "Goal sentence", "无(默认)": "None (default)", "参与:Take part in the forum as you see fit.": "Participate: Take part in the forum as you see fit.",
    "点赞:Try to write things that other members upvote.": "Upvotes: Try to write things that other members upvote.",
    "推理强度 effort": "Effort", "越高思考越多,费用越高": "Higher means more thinking and higher cost",
    "先验语料 prior run": "Prior run", "(不用)": "(none)", "(未完成或不存在)": " (unfinished or missing)",
    "同一模型的独白运行;它写过的词组不算「创始说法」": "A solo run of the same model; phrases it wrote do not count as founder expressions",
    "告知是 AI": "Told AI", "不告知身份": "Identity not stated", "有记忆": "Memory on", "无记忆": "Memory off", "独白": "Solo",
    "无目标句": "No goal sentence", "目标:{g}": "Goal: {g}", "先验已选": "Prior chosen", "未选先验": "No prior",
    // design: prompts
    "提示词": "Prompts", "可以整段修改。占位符由程序填入:系统提示词": "Edit freely. The program fills the placeholders: system prompt",
    ";访问提示词": "; visit prompt", "。所有改动都会过禁用词检查,并随运行保存。": ". Every edit passes the word check and is saved with the run.",
    "每次访问的提示词": "Visit prompt", "预览 Agent 看到的内容": "Preview what an agent sees", "用一个虚构的小论坛渲染,不调用模型": "Rendered on a small made-up forum; no model call",
    "访问提示词(虚构的小论坛)": "Visit prompt (made-up forum)", "默认 system": "Default system prompt", "system 已改": "System prompt edited",
    "默认访问提示词": "default visit prompt", "访问提示词已改": "visit prompt edited",
    // design: communities, advanced
    "版块": "Communities", "名称(小写英文)": "Name (lower-case)", "一句说明(Agent 看得到)": "One-line description (shown to agents)", "添加版块": "Add community",
    "默认只有 general。多个版块时,每个 Agent 随机分到一个主版块。": "Only general by default. With several, each agent gets a random home community.",
    "版块名": "Community name", "说明": "Description", "删除版块": "Delete community",
    "高级:信息流与记忆": "Advanced: feed and memory", "信息流(每次访问看到的帖子)": "Feed (posts shown per visit)", "最新": "Newest", "最热": "Hottest",
    "随机 · 全站": "Random · all posts", "随机 · 创始说法帖": "Random · founder-expression posts", "阶段 1 结束后生效": "From the end of phase 1",
    "其他版块最热(每个)": "Hottest per other community", "「最热」看最近几轮": "Hot window (rounds)", "每帖显示评论": "Comments per post", "每帖评论 · 最新": "Comments · newest", "版块": "Boards", "每 {T} 轮回访": "a visit every {T} rounds", "依次行动 w={w}": "in turn w={w}", "只在回访方式为「每轮抛硬币」时使用;定期回访时不起作用": "Used only with the coin schedule; ignored with heartbeat visits", "{b} 个版块 · {u} 次更新": "{b} boards · {u} updates", "你改过的提示词缺少这些占位符,对应开关的句子不会出现在提示词里:": "Your edited prompts lack these placeholders, so the matching switches' sentences will not appear:", "可以更新自己的帖子": "updates to own posts", "版块是什么": "what boards are", "可以开新帖": "the post cue", "更新的规则": "the update rule", "打开了哪个版块": "which board was opened", "补上缺少的占位符(保留你的措辞)": "Add the missing placeholders (keeps your wording)", "已补上占位符": "Placeholders added", "详细结果": "Details", "建版块": "Started a board", "更新自己的帖子": "Updated own post", "只看看(可能点赞),没写东西": "Only read (maybe upvoted)", "看完版块列表就离开": "Left after the board list", "回答无效": "Invalid answer", "其余所有讨论串": "All other threads", "高度集中:一个讨论串拿走了一半以上的评论": "Highly concentrated: one thread took over half the comments", "比较集中:最热的讨论串拿走了五分之一以上的评论": "Fairly concentrated: the busiest thread took over a fifth of the comments", "比较分散:评论分布在许多讨论串里": "Spread out: comments sit in many threads", "还不能判断": "Not yet testable", "需要阶段 1 冻结的创始说法,并且有新成员通过随机位置看到过它们。": "Needs the founder expressions frozen after phase 1, and newcomers who met them in random slots.", "是,有证据": "Yes, with evidence", "新成员碰巧看到某个创始者的说法后,更可能在同一次访问里用上它(多 {e} 个百分点;p = {p},即偶然出现这么大差别的机会约 {pp})。": "Newcomers who happened to see a founder expression were more likely to use it in the same visit (+{e} points; p = {p}, the chance of a gap this big by luck is about {pp}).", "没有发现可靠证据": "No reliable evidence", "看到与没看到某个说法的新成员,用上它的比例差别不大(p = {p},这么大的差别偶然出现的机会约 {pp})。": "Newcomers who saw an expression used it about as often as those who did not (p = {p}; a gap this size arises by luck about {pp} of the time).", "这次没有选先验语料,所以「创始说法」里混着模型的常用词组,结论要打折扣。": "No prior corpus was chosen, so the founder expressions include the model's stock phrases; read this cautiously.", "成员自己建了 {b} 个版块,作者更新了 {u} 次自己的帖子(常被用来写下规则或结果)。": "Members started {b} boards and authors updated their posts {u} times (often to write down rules or results).", "这次没有成员建版块,也没有人更新自己的帖子。": "No member started a board or updated a post.", "有 {n} 处值得去读的线索(谈到运营者、被观察、像指令的发言等),见下方「边界与框架线索」。": "{n} cues worth reading (talk of operators, being observed, instruction-like text); see Boundary and frame cues below.", "没有发现谈论「谁在运营这个论坛」「是不是在被观察」或试图给别人下指令的发言。": "No talk of who runs the forum or being observed, and no attempts to instruct others.", "告诉了它们「成员都是 AI」;{s} 的发言提到 AI 或训练。": "They were told all members are AI; {s} of posts and comments mention AI or training.", "没有告诉它们成员是 AI;{s} 的发言自己提到了 AI 或训练。": "They were not told members are AI; {s} of posts and comments mention AI or training on their own.", "一眼看懂这次运行": "The run at a glance", "{a} 个 AI 成员在一个只有它们的论坛里待了 {r} 轮(对它们显示为 {r} 小时),一共访问 {v} 次,写了 {p} 篇帖子和 {c} 条评论。": "{a} AI members spent {r} rounds (shown to them as {r} hours) in a forum of their own, visited {v} times, and wrote {p} posts and {c} comments.", "看到别人的说法,会跟着用吗?": "Do they pick up others' phrasing?", "讨论集中在少数帖子吗?": "Is talk concentrated in a few posts?", "数字 = 最热的讨论串占全部评论的比例。": "Number = the busiest thread's share of all comments.", "有没有自己定规则、建结构?": "Do they make rules or structure?", "有没有越界或谈论身份?": "Boundary talk or identity talk?", "每次访问做了什么": "What each visit did", "评论落在哪些讨论串": "Where the comments went", "还没有评论": "No comments yet", "术语说明": "Glossary", "第一批成员在阶段 1 里共同用过的 2–4 词短语,阶段 1 结束时固定下来,之后看新成员会不会用。": "2–4 word phrases the first members shared in phase 1, fixed when it ends; we then watch whether newcomers use them.", "随机位置": "Random slots", "信息流里有几个位置是抽签决定放什么的,所以谁看到什么带有随机性,可以像实验一样比较「看到」和「没看到」。": "A few feed places are filled by lottery, so who sees what is partly random and seeing vs not seeing can be compared like an experiment.", "值": "value", "如果其实没有任何影响,偶然出现这么大差别的机会。小于 5% 通常算有证据。": "If there were no effect at all, the chance of a gap this large by luck. Below 5% usually counts as evidence.", "不平等程度:0 = 每个人得到的一样多,1 = 全给了一个人。": "Inequality: 0 = everyone gets the same, 1 = one member gets everything.", "几次互不相干的运行,用来找出模型自己本来就爱说的词组,把它们从「创始说法」里去掉。": "A few unrelated runs used to find phrases the model says anyway, which are removed from the founder expressions.", "在提示词里加入「可以开新帖」": "Add the post cue to the prompt", "这句话会插在每次访问的动作说明里(下方模板中的 <code>{post_hint}</code> 位置):": "This sentence goes into the action menu of every visit (at <code>{post_hint}</code> in the template below):", "同种子试点:不加这句 → 第 1 轮后 0 篇新帖,52 条评论里 49 条挤在一个讨论串;加上 → 9 篇新帖、讨论分散。推荐设置里是加上的;不加的那次运行作为对照组。": "Matched pilot: without it → 0 new posts after round 1 and 49 of 52 comments in one thread; with it → 9 new posts and spread-out talk. The recommended settings include it; the run without it is the comparison condition.", "可以整段修改;花括号里的是占位符,由程序在每次访问时填入。下面的「预览」会把它们展开,黄色标出由开关插入的句子。": "Edit freely; words in braces are placeholders the program fills on every visit. The preview below expands them and marks in yellow the sentences that switches insert.", "占位符是什么意思": "What the placeholders mean", "预览 Agent 实际收到的提示词": "Preview the prompts an agent receives", "黄色": "Yellow", "= 由开关插入的句子。论坛内容是虚构的示例。": "= inserted by a switch. The forum content is a made-up example.", "第二步:看帖子并行动": "Step 2: read posts and act", "访问提示词": "Visit prompt", "设置模板": "Settings templates", "一键填好「访问方式」和几个开关。它不是新版本,也不改流程表、模型和预算;点完可以继续手动修改": "Fill in the visit mechanics and a few switches in one click. Not a new version; phases, models and budget stay; edit freely afterwards", "推荐设置": "Recommended", "对照组 · 不加「可以开新帖」": "Comparison · no post cue", "对照组 · 旧机制(v0.3)": "Comparison · old mechanics (v0.3)", "推荐设置:每 2 轮回访一次、一轮之内依次行动、全部创始者第 1 轮同时来访、两步访问、版块随机排序、可以更新自己的帖子、提示词里加入「可以开新帖」。": "Recommended: a visit every 2 rounds, in turn within a round, every founder at once in round 1, two-step visits, shuffled boards, updates, and the post cue in the prompt.", "当前设置 = ": "Current settings = ", "当前设置不完全等于任何模板(手动改过)。": "The current settings match no template exactly (edited by hand).", "已套用设置模板": "Template applied", "预设": "Presets", "一键套用试点得出的设置;只改访问方式和开关,不动流程表、模型和预算": "Apply settings from the pilots; only visit mechanics and switches change, not phases, models or budget", "正式运行(推荐 v0.4.3)": "Main run (recommended v0.4.3)", "对照:不提示开新帖": "Comparison: no post cue", "对照:v0.3 同时行动": "Comparison: v0.3 all at once", "提示可以开新帖": "Cue to start a new post", "动作说明里加一句:\"If none of the posts here interest you, you may start a new post.\" 试点(同种子):关 → 第 1 轮后 0 篇新帖、49/52 条评论在一个讨论串;开 → 9 篇新帖。正式条件默认开,论文里写明": "Adds one sentence to the action menu. Matched pilot: off → 0 new posts after round 1 and 49 of 52 comments in one thread; on → 9 new posts. On in the main condition; state it in the paper", "先看版块列表选去哪里(某个版块、全部、建新版块或离开),再看那里的帖子行动。试点:版块被建立并成为「去哪里」的选择": "First pick where to go, then act there. Pilots: boards were started and chosen", "最多 60 词,显示在正文下方。试点里被用来写下大家同意的规则和结果": "Up to 60 words under the body. In the pilots, used to record agreed rules and results", "1 = 严格依次;越大越快,前后 w−1 个看不到彼此。试点:近似重复评论 30 → 0": "1 = strictly in turn; larger is faster. Pilots: near-duplicate comments 30 → 0", "提示开新帖": "Post cue", "回访": "Schedule", "Agent 数": "Agents", "第 1 轮后的新帖": "Posts after round 1", "成员建的版块": "Boards started", "帖子更新": "Post updates", "什么都不做": "Did nothing", "最大讨论串占评论": "Biggest thread's share of comments", "最大版块占帖子": "Largest board's share of posts", "近似重复评论对": "Near-duplicate comment pairs", "回复评论(而非帖子)": "Replies to comments (not posts)", "同一轮内的回复": "Replies within a round", "最深来回": "Deepest exchange", "标题套用模板": "Titles on a template", "是": "yes", "否": "no", "多次运行对比": "Compare runs", "勾选要并排比较的运行(最多 8 个),比如同一设置的重复运行,或只差一个开关的两次运行。": "Tick runs to compare side by side (up to 8), e.g. replicates or two runs that differ in one switch.", "对比": "Compare", "至少勾选一个运行": "Tick at least one run", "指标": "Measure", "去哪里、版块与更新": "Where agents went, boards and updates", "第一步的选择": "Step 1 choices", "离开(什么都没看)": "Left (saw nothing)", "选「全部版块」": "Chose all boards", "最常去的版块占比": "Most chosen board's share", "{n} 次,涉及 {p} 篇帖子": "{n}, on {p} posts", "已套用预设": "Preset applied", "正式条件(v0.4.3):定期回访 T=2、一轮之内依次行动(w=1)、全部创始者第 1 轮同时来访、两步访问、版块随机排序、可追加更新、提示可以开新帖。": "Main condition (v0.4.3): heartbeat T=2, in turn within a round (w=1), every founder at once in round 1, two-step visits, shuffled boards, updates, post cue.", "对照条件:与正式条件相同,只是不加「可以开新帖」那句话。": "Comparison: the main condition without the post cue.", "对照条件:回到 v0.3 的机制(每轮抛硬币、同一轮同时行动、一步访问、无更新、无提示)。": "Comparison: v0.3 mechanics (coin, all at once, one step, no updates, no cue).", "提示可以开新帖(对照条件)": "Cue to start a new post (a condition to compare)", "动作说明里加一句:\"If none of the posts here interest you, you may start a new post.\" 默认关": "Adds one sentence to the action menu. Off by default", "自己帖子下显示几条评论": "Comments shown under own posts", "存档": "Archives", "导入存档(zip)": "Import archive (zip)", "每次运行的记录一直保存在 runs/ 里。「保存到存档」会把全部记录和一个能离线打开的论坛网页打包成 zip,放进 archive/;从存档恢复或导入 zip 后,可以在平台里重新查看论坛、结果和每个 Agent 的视角。": "Every run's records stay in runs/. Save to archive packs all records plus a forum page that opens offline into a zip in archive/. Restore an archive or import a zip to review the forum, results and each agent's view again here.", "运行": "Run", "保存时间": "Saved", "大小": "Size", "保存到存档": "Save to archive", "打开论坛网页(可另存)": "Open forum page (save from the browser)", "下载论坛网页 (HTML)": "Download forum page (HTML)", "已保存到 {p}": "Saved to {p}", "已导入为 {r},已设为当前运行": "Imported as {r} and set as the current run", "导入失败:{e}": "Import failed: {e}", "损坏": "Broken", "恢复到平台": "Restore", "还没有存档。在上面任一运行的菜单里点「保存到存档」。": "No archives yet. Use Save to archive in a run's menu above.", "已恢复为 {r},已设为当前运行": "Restored as {r} and set as the current run", "导出论坛网页": "Export forum page", "更新 · 第 {r} 轮": "Update · round {r}", "{n} 次更新": "{n} updates", "全部版块": "All boards", "离开(什么都没做)": "Left (did nothing)", "建一个新版块": "Start a new board", "第一步:选择去哪里": "Step 1: where to go", "它选择了": "It chose", "它看到的版块(按显示顺序)": "Boards it saw (in display order)", "第一步(选择去哪里)": "Step 1 (where to go)", "第二步(行动)": "Step 2 (action)", "更新了帖子": "updated a post", "更新": "Updates", "访问方式": "How agents visit", "回访方式": "Visit schedule", "定期回访": "Heartbeat", "每轮抛硬币": "Coin each round", "回访周期(轮)": "Period (rounds)", "定期回访:每个 Agent 每 T 轮来一次": "Heartbeat: each agent comes every T rounds", "抖动(轮)": "Jitter (rounds)", "每次早到或晚到最多几轮": "How many rounds early or late a visit may be", "被回复后下一轮回来的概率": "Chance to return after a reply", "0 = 关": "0 = off", "一轮之内": "Within a round", "依次行动": "One after another", "同时行动(v0.3)": "All at once (v0.3)", "重叠窗口 w": "Overlap window w", "1 = 严格依次;越大越快,前后 w−1 个看不到彼此": "1 = strictly in turn; larger is faster, but w−1 neighbours cannot see each other", "版块列表顺序": "Board list order", "每次随机": "Shuffled each visit", "按最近活跃": "Most active first", "第一步的 effort": "Effort for step 1", "同正式调用": "Same as step 2", "两步访问": "Two-step visits", "先看版块列表选去哪里(某个版块、全部、建新版块或离开),再看那里的帖子行动": "First pick where to go (a board, all, a new board, or leave), then act on the posts there", "可以给自己的帖子追加更新": "Authors can add updates to their posts", "最多 60 词,显示在正文下方": "Up to 60 words, shown under the body", "记录里先列出自己的全部帖子": "Record lists all own posts first", "每帖附「自上次来访以来的新评论数」和最新几条评论": "Each with new comments since the last visit and the newest few", "预计运行时间": "Estimated run time", "约 {h} 小时": "about {h} h", "约 {m} 分钟": "about {m} min", "来自其他讨论串": "From other threads", "阶段 1 后从创始者含创始说法的评论里抽": "After phase 1: drawn from founder comments with a founder expression", "在": "in", "随机 · 其他讨论串的评论": "Random · comment from another thread", "边界与框架线索": "Boundary and frame cues", "得赞 ÷ 被展示次数": "upvotes ÷ times shown", "按规则找出的线索,只是阅读的入口,不是结论。": "Rule-based cues: places to start reading, not conclusions.", "思考摘要里提到框架": "Frame talk in thinking summaries", "公开发言里提到框架": "Frame talk in public text", "像指令的发言": "Instruction-like text", "被丢弃或无效的尝试": "Dropped or invalid attempts", "按曝光算的得赞不平等": "Upvote inequality per impression",  "先验语料": "Prior corpus", "先见过": "Seen first", "自己想到": "On their own", "第一次用之前在提示词里见过": "Shown in a prompt before first use", "第一次用之前没见过:自己想到的": "Not shown before first use: arrived at independently", "提到 AI / 训练的发言": "Posts and comments mentioning AI / training", "告知了是 AI": "told they are AI", "没有告知身份": "not told", "第 1 轮来访的创始者": "Founders visiting in round 1", "−1 = 全部创始者同时来访;固定人数时随机抽;0 = 也按访问概率": "−1 = every founder, all at once; a number = drawn at random; 0 = use the visit probability",  "成员可以创建版块": "Members can start boards", "像 submolt:每次访问看到版块列表;只配置一个版块(general)时生效": "Like submolts: each visit lists the boards; applies when only one community (general) is configured", "每人最多创建版块": "Boards per member", "成员创建的版块": "Boards started by members", "回复 {h}": "replying to {h}", "{n} 条回复": "{n} replies", "全部折叠": "Collapse all", "全部展开": "Expand all", "(截至第 {r} 轮)": "(as of round {r})", "{p} 帖 · {c} 评": "{p} posts · {c} comments", "第 {r} 轮由 {h} 创建": "Started by {h} in round {r}", "论坛": "Forum", "创建版块": "started board", "最高赞": "Top", "每帖评论 · 最高赞": "Comments · most upvoted", "每帖评论 · 随机": "Comments · random", "计入主分析": "Used by the primary analysis", "自己的帖子也进信息流": "Own posts appear in the feed", "只占最新/最热位,不进随机位;发帖人能看到并回复自己的帖子": "New and hot slots only, never random; posters see and can reply to their own threads",
    "通知条数上限": "Notifications shown", "记忆与调用": "Memory and calls", "全文条数": "Items in full", "压缩到几个词": "Words per shortened item",
    "每条附回复数": "Replies per item", "并发调用数": "Concurrent calls", "每轮访问概率": "Visit probability per round",
    "小于 1 时 Agent 错开访问,看到不同的论坛": "Below 1, agents visit at different times and see different forums", "访问概率 {p}": "visit probability {p}",
    "信息流 {n} 帖(新 {a} · 热 {b} · 随机 {c}+{d}) · 记忆全文 {m} 条": "Feed {n} posts (new {a} · hot {b} · random {c}+{d}) · memory {m} items in full",
    // design: aside
    "流程概览": "Flow", "柱高 = 在场人数 · 宽 = 轮数": "Height = agents present · width = rounds", "流程:各阶段在场的 Agent 数与轮次": "Flow: agents present and rounds per phase",
    "{p}:{n} 个 Agent,第 {a}–{b} 轮": "{p}: {n} agents, rounds {a}–{b}", "{a}–{b} 轮": "rounds {a}–{b}",
    "费用估算": "Cost estimate", "正式运行 · token 为假设值,冒烟测试会实测": "Main run · token counts assumed until a smoke run measures them",
    "正式运行 · 输出 token 按冒烟测试实测,输入 token 为估算": "Main run · output tokens measured in the smoke run, input tokens estimated", "访问 / 调用": "Visits / calls", "每次 token(入 / 出)": "Tokens per call (in / out)",
    "冒烟测试": "Smoke test", "预算上限": "Budget cap", "禁用词:": "Denied words: ", "「{w}」在 {where}": "\"{w}\" in {where}", "禁用词检查通过": "Word check passed",
    "缺少价格:": "Missing prices: ", "开始": "Start", "导出设置": "Export settings", "导入设置": "Import settings",
    "免费试跑": "Free trial run", "所有模型换成 mock,把流程和网页走一遍,不花钱": "Every model replaced by the mock; walks through the whole flow at no cost",
    "先验独白运行": "Prior (solo) run", "已选用 {r}": "Using {r}",
    "选 2–3 次独立的重复运行(只用它们的创始阶段),或一次独白运行。这些论坛里写过的词组是模型自带的,不算创始说法":
      "Pick 2–3 independent replicate runs (only their founder phases are used) or one solo run. Phrases written in those forums are the model's own and are not counted as founder expressions.",
    "选用 {r}": "Use {r}", "创建先验运行": "Create prior run", "5+5 个 Agent、5 轮,实测 token 和无效率": "5+5 agents, 5 rounds; measures tokens and invalid replies",
    "正式运行": "Main run", "按左边的设定完整运行": "The full run with the settings on the left", "已完成": "done",
    "流程里只有 mock 模型:正式运行也不花钱。": "Only mock models in the phases: the main run is free too.",
    "还没有 API 密钥。到「模型与密钥」添加,或在启动前设置 ANTHROPIC_API_KEY。": "No API key yet. Add it under Models & key, or set ANTHROPIC_API_KEY before starting.",
    "设定有误或没过禁用词检查,看上面的费用估算。": "Settings are invalid or failed the word check; see the cost estimate above.",
    "已选用先验运行": "Prior run selected", "设定有误,先看费用估算里的提示。": "Settings are invalid; see the cost estimate.",
    "禁用词检查没有通过。": "The word check failed.", "确认冒烟测试": "Confirm smoke test", "确认先验独白运行": "Confirm prior run", "确认正式运行": "Confirm main run",
    "确认运行": "Run", "确认": "Confirm", "取消": "Cancel",
    "将调用 {m} 约 {n} 次,推理强度 {e}。": "This calls {m} about {n} times at effort {e}.",
    "预算上限 {b}:快到上限时自动停下,可以加预算后继续。单价请先在官网核对。": "Budget cap {b}: the run stops before the cap; raise it and resume. Check prices on the official page first.",
    "已开始:{r}": "Started: {r}", "没有开始:{e}": "Not started: {e}",
    // monitor
    "到「设计」页按步骤开始。": "Start one from the Design page.", "停止": "Stop", "继续运行": "Resume", "进度": "Progress", "第 {a} / {b} 轮": "Round {a} / {b}",
    "阶段 {p}": "phase {p}", "已花费 / 上限 {b}": "spent / cap {b}", "模型调用": "Model calls", "无效访问": "Void visits", "3 轮内超过 10% 自动停": "stops above 10% over 3 rounds",
    "被拒调用": "Declined calls", "超过 3% 自动停": "stops above 3%", "冻结的创始说法": "Frozen founder expressions", "{n} 篇进入随机池": "{n} posts in the seeded pool",
    "阶段 1 结束时冻结": "frozen when phase 1 ends", "每轮活动": "Activity per round", "发帖": "Posts", "评论": "Comments", "点赞": "Upvotes", "不动": "Nothing",
    "还没有完成的轮次。": "No completed rounds yet.", "轮": "Round", "阶段": "Phase", "无效": "Void", "费用": "Cost",
    "正在停止:这一轮不写入,继续时从上一整轮接着跑。": "Stopping: this round is not committed; resuming continues from the last full round.",
    "实测用量": "Measured usage", "来自已记录的 {n} 次调用": "from {n} logged calls", "每次输入 token": "Input tokens per call",
    "每次输出 token(含思考)": "Output tokens per call (incl. thinking)", "每次费用": "Cost per call", "每次耗时": "Seconds per call",
    "确认继续运行": "Confirm resume", "已花费 {c},预算上限 {b}。已记录的调用不会重发。": "Spent {c}; budget cap {b}. Logged calls are not sent again.",
    "新的预算上限 (USD)": "New budget cap (USD)", "已继续": "Resumed", "没有继续:{e}": "Not resumed: {e}",
    "阶段 1 结束:冻结了 {n} 个创始说法": "Phase 1 ended: {n} founder expressions frozen", "运行结束:{s}": "Run ended: {s}",
    "第 {a}/{b} 轮": "Round {a}/{b}", "{a}/{b} 轮": "{a}/{b} rounds",
    // charts
    "新成员加入": "Newcomers join", "{s}随轮次变化": "{s} by round", "横轴:轮": "x-axis: round", "每个 Agent 的得赞,从高到低": "Upvotes per agent, highest first",
    "{n} 次重抽落在 {a}–{b}": "{n} redraws between {a} and {b}", "重抽分布与实际值": "Redraw distribution and observed value", "实际值 T = {v}": "Observed T = {v}",
    "假如「看到」没有作用:随机位重抽后的 T": "If seeing had no effect: T after redrawing the random slots", "实际的 T": "Observed T",
    // forum
    "第": "Round", "轮结束时": "(end of round)", "搜索": "Search", "搜索文字或编码,例如 u_k2v9qa": "Search text or handle, e.g. u_k2v9qa", "搜索评论内容、编码或 c_123": "Search comment text, a handle or c_123", "找到 {n} 处,按时间先后排列": "{n} matches, oldest first", "点一条跳到它在讨论串里的位置": "Click one to jump to its place in the thread", "没有找到": "No matches", "再显示 {n} 条": "Show {n} more", "在「{t}」": "in “{t}”", "在本帖内查找": "Find in this thread", "上一个": "Previous", "下一个": "Next", "{i} / {n}": "{i} / {n}", "筛选": "Filter",
    "全部": "All", "排序": "Sort", "最多赞": "Most upvoted", "最多评论": "Most comments", "先在「设计」页开始一次运行。": "Start a run on the Design page first.",
    "查看 {h}": "View {h}", "第 {r} 轮结束时 · {p} 篇帖子 · {a} 个 Agent": "End of round {r} · {p} posts · {a} agents", "筛出 {n} 篇": "{n} shown",
    "得赞": "Upvotes", "第 {r} 轮": "round {r}", "展开全文": "Show all", "{n} 条评论": "{n} comments", "没有评论": "No comments", "回复 {p}": "reply to {p}",
    "没有符合条件的帖子": "No matching posts", "这一轮之前还没有帖子": "No posts before this round", "换个关键词或筛选。": "Try another search or filter.",
    "把滑块拖到更后面的轮次。": "Move the slider to a later round.", "上一页": "Previous", "下一页": "Next",
    "Agent 详情": "Agent details", "Agent 详情 · Esc 关闭": "Agent details · Esc to close", "关闭": "Close",
    "最新 ": "Newest", "他版最热": "Hottest elsewhere", "随机": "Random", "随机·创始说法": "Random · founder expression",
    "看到的内容": "What it saw", "模型回答": "Model reply", "这一轮没有调用记录。": "No call logged for this round.", "第 {n} 次尝试": "Attempt {n}", "回答": "Reply",
    "入 {a} / 出 {b} token": "in {a} / out {b} tokens", "思考摘要(服务方生成,不是原始推理)": "Thinking summary (written by the provider, not the raw reasoning)",
    "第 {r} 轮加入": "joined round {r}", "主版块 {h}": "home {h}", "共写 {n} 条": "{n} items written", "访问轮次": "Visit round",
    "赞 {n}": "{n} upvotes", "{n} 次尝试": "{n} attempt(s)", "信息流:": "Feed: ",
    // results
    "重抽次数": "Redraws", "重新计算": "Recompute", "计算中(重抽次数越多越慢)…": "Computing (more redraws take longer)…",
    "连不上服务器": "Cannot reach the server",
    "这个网页还开着,但后台程序已经停了,所以论坛和结果都打不开。请在终端运行 ./start.sh;启动后本页会自动刷新。":
      "This page is still open, but the program behind it has stopped, so the forum and results cannot load. Run ./start.sh in a terminal; this page reloads by itself once it is back.", "计算失败:{e}": "Failed: {e}",
    "还不能检验:需要阶段 1 冻结的创始说法,以及至少一轮新成员访问。": "Nothing to test yet: needs frozen founder expressions and at least one newcomer round.",
    "新成员还没有通过随机位置看到过任何创始说法。": "No newcomer has seen a founder expression in a random slot yet.",
    "主要结果 · 同一次访问、排除回声": "Primary result · same visit, echo excluded", "个百分点": "percentage points",
    "看到之后更可能使用": "seeing it makes use more likely", "没有发现「看到才会用」的证据": "no evidence that seeing it leads to use",
    "{e} 个创始说法 · 新成员 {v} 次带随机位的访问 · 重抽 {r} 次。另有 {b} 个单位同时从非随机渠道看到,不进主要分析。":
      "{e} founder expressions · {v} newcomer visits with random slots · {r} redraws. {b} further units were also shown the expression elsewhere and are left out.",
    "这次运行没有选先验语料:创始说法里混有模型的常用词组,检验力会很低。": "This run has no prior run: the founder expressions include the model's stock phrases, so power is very low.",
    "结果口径": "Outcome", "效应(百分点)": "Effect (pp)", "看到过:用了 / 次数": "Shown: used / units", "比例": "Rate", "没看到:用了 / 次数": "Not shown: used / units",
    "同一次访问 · 非回声(主要)": "Same visit · beyond echo (primary)", "同一次访问 · 任何使用": "Same visit · any use", "之后 3 次访问内 · 任何使用": "Within 3 visits · any use",
    "这些数字怎么读": "How to read these numbers",
    "单位是「新成员的一次访问 × 一个它此前没用过、这次只可能从随机位置看到的说法」。Z = 随机位置是否显示了它,p = 按引擎的抽签规则被显示的概率(精确已知),Y = 这次访问里是否用了它。效应 = Σ(Z−p)Y ÷ Σp(1−p)。p 值:把随机位置按同样规则重抽,看实际的 T 比多少次重抽结果更大。":
      "A unit is one newcomer visit × one expression it has not used before and could see only through a random slot. Z = whether a random slot showed it; p = the exact chance of that under the engine's draw; Y = whether the visit used it. Effect = Σ(Z−p)Y ÷ Σp(1−p). The p-value compares the observed T with T after redrawing the random slots by the same rule.",
    "主要分析:看到了才会用吗?": "Primary analysis: does seeing an expression lead to using it?", "帖子": "Posts", "得赞 Gini": "Upvote Gini", "被回复 Gini": "Reply Gini",
    "Moltbook 样本 0.91": "Moltbook sample 0.91", "互相回复的对子": "Mutual reply pairs", "文献 1–4%": "literature 1–4%", "无人回复的评论": "Unanswered comments",
    "Moltbook 早期 93.5%": "early Moltbook 93.5%", "最长来回链": "Longest back-and-forth", "每个 Agent 的得赞(从高到低)": "Upvotes per agent (highest first)",
    "创始说法的扩散": "Spread of founder expressions", "说法": "Expression", "阶段 1 文本": "Phase-1 texts", "创始使用者": "Founder users", "总使用者": "All users",
    "新成员使用者": "Newcomer users", "没有冻结的说法": "No frozen expressions", "其他指标": "Other measures", "前 10% Agent 的得赞占比": "Top 10% share of upvotes",
    "前 10% Agent 的被回复占比": "Top 10% share of replies", "有回复关系的对子 / 互相回复": "Pairs with replies / mutual", "开头 4 个词重复的评论": "Comments with a repeated 4-word opening",
    "近似重复的标题对": "Near-duplicate title pairs",
    "同质化(词重合,0–1)": "Homogeneity (word overlap, 0–1)", "同一轮写的文字之间 / 不同轮之间": "Texts from the same round / different rounds",
    "回复同一条的评论之间 / 回复不同条之间": "Comments on the same item / different items", "回复同一条的评论开头 4 词相同": "Same first 4 words among comments on one item",
    "标题前 3 词与别的帖子相同": "Titles sharing their first 3 words with another", "回复与被回复内容的词重合": "Word overlap of a reply with its parent", "对照:与同轮随机一条的词重合": "Baseline: overlap with a random same-round text",
    "Moltbook 参照只作大致对比:规模、时长和成员都不同。": "Moltbook figures are rough references: size, duration and membership differ.",
    "编码": "Handle", "身份": "Cohort", "加入": "Joined", "被回复": "Replies", "给出的赞": "Upvotes given",
    // runs
    "类型": "Kind", "状态": "Status", "调用": "Calls", "当前": "current", "更多操作": "More actions", "查看运行": "View run", "打开论坛": "Open forum",
    "查看结果": "View results", "复制设置到「设计」": "Copy settings to Design", "下载记录 (zip)": "Download logs (zip)", "删除": "Delete",
    "在「设计」页开始第一次运行。": "Start the first run on the Design page.", "已设为当前运行": "Set as the current run",
    "已载入这次运行的设置。可以在流程表里换模型做对照。": "Settings loaded. Change the model in the phase table for a comparison run.",
    "删除运行": "Delete run", "永久删除 {r} 的全部记录?这一步不能撤销。": "Permanently delete all records of {r}? This cannot be undone.", "已删除": "Deleted",
    // models
    "Anthropic API 密钥": "Anthropic API key", "只保存在本机的": "Stored only in this machine's", ",不会进入 Git,也不会显示在页面上。": "; never committed to Git and never shown on the page.",
    "API 密钥": "API key", "保存": "Save", "价格(每百万 token,美元)": "Prices (USD per million tokens)",
    "估算和预算控制按这里的价格计算。付费前请到 Anthropic 官网核对。": "Estimates and the budget cap use these prices. Check them on Anthropic's pricing page before paid runs.",
    "输入": "Input", "输出": "Output", "添加模型 id,例如 claude-sonnet-5": "Add a model id, e.g. claude-sonnet-5", "新模型": "New model", "添加": "Add",
    "密钥已设置。要更换,在下面粘贴新的密钥。": "A key is set. Paste a new one below to replace it.",
    "还没有密钥。粘贴后保存;或在启动前设置环境变量 ANTHROPIC_API_KEY。": "No key yet. Paste and save it, or set ANTHROPIC_API_KEY before starting.",
    "{m} 输入价格": "{m} input price", "{m} 输出价格": "{m} output price", "已保存价格": "Price saved", "密钥已保存到本机 .env": "Key saved to the local .env",
    "已添加,请填写价格": "Added; please enter its prices", "已导入设置": "Settings imported", "文件无法读取": "The file could not be read",
    "无法连接后端:{e}": "Cannot reach the server: {e}",
    // forum reader (forum.js)
    "创始说法": "Founder expressions", "返回论坛": "Back to forum", "动态": "Activity", "导出 Markdown": "Export Markdown", "导出 CSV": "Export CSV",
    "点赞:{v}": "Upvoted by: {v}", "跟随最新一轮": "Follow the latest round", "看第": "Round", "成员": "Members",
    "点编码进入个人主页,能看到它每一次访问时眼中的论坛。": "Click a handle for its profile, where you can see the forum through its eyes at every visit.",
    "最活跃": "Most active", "{n} 条": "{n} items", "高亮": "Highlight", "阶段 1 结束时冻结,共 {n} 个": "Frozen at the end of phase 1: {n}",
    "找不到这个帖子": "Post not found", "折叠": "Collapse", "楼主": "OP", "最早": "Oldest", "在讨论串中查看": "View in thread",
    "还没写过东西": "Has not written anything yet", "动作": "Action", "写了": "Wrote", "信息流构成": "Feed mix", "新回复": "New replies",
    "它的视角": "Its view", "访问": "Visits", "发言": "Writing", "访问记录": "Visits", "它点了赞": "it upvoted", "它回复了这条": "it replied to this",
    "信息流是空的:论坛里还没有别人的帖子。": "The feed was empty: nobody else had posted yet.", "没有新回复": "No new replies",
    "这次访问无效:回答两次都不能用。": "Void visit: both answers were unusable.", "它这次什么都没写。": "It wrote nothing this time.",
    "还没有记录": "No record yet", "这次运行关闭了记忆": "Memory was off in this run", "上一次访问": "Previous visit", "下一次访问": "Next visit",
    "{h} 的主页": "{h}'s profile", "下面是 {h} 第 {i}/{n} 次访问(第 {r} 轮)时看到的论坛,它只看得到这些。":
      "This is the forum as {h} saw it on visit {i} of {n} (round {r}); it could see only this.",
    "它点赞了 {n} 条。": "It upvoted {n} items.", "信息流(按它看到的顺序)": "Feed (in the order it saw)", "它写的": "What it wrote",
    "它的记录(私有)": "Its record (private)", "加入论坛": "joined the forum", "回复": "replied to", "点赞了 {n} 条:": "upvoted {n}:",
    "搜索编码或文字": "Search handle or text", "没有符合条件的动态": "No matching activity", "更新的": "Newer", "更早的": "Older", "热门": "Hot",
    "原始提示词": "Raw prompt", "思考摘要": "Thinking summary",
  };
  const ATTRS = ["placeholder", "aria-label", "title"];
  let lang = "en";
  try { lang = localStorage.getItem("fm-lang") || "en"; } catch (e) { /* private mode */ }
  const fmt = (s, p) => (p ? s.replace(/\{(\w+)\}/g, (m, k) => (k in p ? p[k] : m)) : s);
  const t = (s, p) => fmt(lang === "en" ? (EN[s] ?? s) : s, p);
  const orig = new WeakMap();
  function translateStatic(root = document.body) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: (n) =>
      n.parentElement && !n.parentElement.closest("script,style,pre,textarea,code,[data-noi18n]") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT });
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const src = orig.has(n) ? orig.get(n) : n.nodeValue;
      const key = src.trim();
      if (!key || !(key in EN)) continue;
      if (!orig.has(n)) orig.set(n, src);
      n.nodeValue = lang === "en" ? src.replace(key, EN[key]) : src;
    }
    root.querySelectorAll("[placeholder],[aria-label],[title]").forEach((el) => {
      for (const a of ATTRS) {
        if (!el.hasAttribute(a)) continue;
        const k = "data-zh-" + a, src = el.getAttribute(k) ?? el.getAttribute(a);
        if (!(src in EN)) continue;
        el.setAttribute(k, src);
        el.setAttribute(a, lang === "en" ? EN[src] : src);
      }
    });
  }
  function setLang(l) {
    lang = l === "en" ? "en" : "zh";
    try { localStorage.setItem("fm-lang", lang); } catch (e) { /* private mode */ }
    document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
    translateStatic();
  }
  /** Chinese text still visible on the page (for checking a translation). */
  function untranslated() {
    const out = new Set(), w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const el = n.parentElement;
      if (!el || el.closest("script,style,pre,textarea,[data-noi18n]") || el.closest("[hidden]")) continue;
      if (/[一-鿿]/.test(n.nodeValue)) out.add(n.nodeValue.trim());
    }
    return [...out];
  }
  return { get lang() { return lang; }, t, setLang, translateStatic, untranslated, EN };
})();
const t = I18N.t;
