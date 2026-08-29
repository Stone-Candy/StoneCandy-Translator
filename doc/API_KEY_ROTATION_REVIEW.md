# API 轮询行为 Review 清单

日期：2026-06-12

这份文档只写本次应该 review 的行为，不按代码实现展开。

## 总体行为

- 只改桌面 Qt 端的 API 管理和运行时 API 使用行为。
- Web 端页面保持原样。
- 不新增配置文件，继续使用现有 `.env`。
- 现有 API 预设要能保存和恢复 API 轮询相关配置。
- OpenAI 和 Gemini 都支持轮询。
- 轮询不只覆盖渲染器，也覆盖翻译、OCR、上色、渲染。

## API 管理页

- API 管理页不再一直显示所有 API。
- 显示内容要和当前设置同步：
  - 当前翻译器是 OpenAI/OpenAI HQ 时，显示翻译 OpenAI。
  - 当前翻译器是 Gemini/Gemini HQ 时，显示翻译 Gemini。
  - 当前 OCR 或备用 OCR 是 OpenAI OCR/Gemini OCR 时，显示对应 OCR API。
  - 当前上色器是 OpenAI/Gemini 时，显示对应上色 API。
  - 当前渲染器是 OpenAI/Gemini 时，显示对应渲染 API。
- 如果当前功能不需要 OpenAI/Gemini API Key，不显示无关输入框，只显示空状态提示。
- 切换翻译器、OCR、上色器、渲染器后，API 管理页要刷新为对应 API 分组。

## API 通道

- 每个 API 分组默认显示 3 个通道。
- 通道 1 继续使用原来的变量名：
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL`
  - `OPENAI_API_BASE`
- 通道 2 开始使用数字后缀：
  - `OPENAI_API_KEY_2`
  - `OPENAI_MODEL_2`
  - `OPENAI_API_BASE_2`
- 后续通道依次使用 `_3`、`_4`。
- 点击 `+` 可以继续添加同样结构的 API 通道。
- 新增通道后，`+` 按钮保持在通道列表底部。
- 每个通道都能单独填 key、model、base。
- 测试连接和获取模型要能识别带 `_2/_3` 后缀的通道。

## 轮询策略

- 每个功能/provider 都有自己的策略，不共用：
  - 翻译 OpenAI
  - 翻译 Gemini
  - OCR OpenAI
  - OCR Gemini
  - 上色 OpenAI
  - 上色 Gemini
  - 渲染 OpenAI
  - 渲染 Gemini
- 策略保存在 `.env`，例如：
  - `OPENAI_API_ROTATION_STRATEGY`
  - `OCR_OPENAI_API_ROTATION_STRATEGY`
  - `COLOR_GEMINI_API_ROTATION_STRATEGY`
  - `RENDER_OPENAI_API_ROTATION_STRATEGY`
- 当前支持两种策略：
  - `failover`
  - `round_robin`

## failover 行为

- 每次请求都从第一个可用通道开始试。
- 如果第一个通道为空、不可用或请求失败，会继续尝试第二个通道。
- 如果第二个也失败，会继续尝试第三个。
- 下一次翻译/OCR/上色/渲染请求，仍然重新从第一个可用通道开始。
- 这对应你说的行为：
  - 第一个 key 空回了就换第二个。
  - 下一个翻译还是从第一个开始试。

## round_robin 行为

- 每次请求会轮流从不同可用通道开始。
- 不可用或冷却中的通道会被跳过。
- 适合多个 key 都正常时分散请求。

## 重试次数和轮询策略

- 重试次数和 API 轮询不是同一个计数。
- 重试次数在轮询内部生效，按“当前 key”计算。
- 当前 key 没有拿到有效结果或抛出 API 错误时，会先用完自己的重试次数，仍失败才切到下一个 key。
- 因此 `attempts=2` 时，含义是每个 key 最多 1 次首次请求 + 2 次重试，也就是最多 3 次。
- 如果有 3 个 key，`failover` 最坏情况下最多会产生 `3 个 key x 3 次 = 9 次` 实际 API 调用。
- 空 key 不参与候选，不消耗 key 调用。
- 400/404/402/billing/quota 这类长期不可用错误，不继续浪费当前 key 的重试次数，直接标记不可用并切下一个 key。
- 429/rate limit 这类临时限流错误，会先按当前 key 的重试次数重试；如果仍失败，再进入冷却并切下一个 key。
- 其他 API 错误，例如返回空内容、没拿到图片/OCR/文本，也会在当前 key 重试耗尽后切下一个 key。
- `attempts=-1` 表示当前 key 无限重试；在这种配置下，当前 key 不会因为重试次数耗尽而自动切到下一个 key。

示例：`attempts=2`，策略为 `failover`，有 3 个 key。

- key1 第 1 次返回空内容，继续重试 key1。
- key1 第 2 次仍返回空内容，继续重试 key1。
- key1 第 3 次仍失败，才切到 key2。
- key2 也最多尝试 3 次，失败后再切 key3。
- 下一张图或下一次翻译请求是新的请求，会重新按策略开始。

## 不可用检测

- 请求返回或异常中检测到以下情况时，对应通道会进入临时冷却：
  - HTTP 429
  - rate limit
  - too many requests
- 429 有可能是服务器繁忙或临时限流，不会被当成 key 永久不可用。
- 冷却中的通道会临时跳过，冷却过期后自动重新参与候选。
- 如果响应头里有 `Retry-After`，按 `Retry-After` 冷却；否则默认冷却 60 秒。
- 请求返回或异常中检测到以下情况时，对应通道会被标记为不可用：
  - HTTP 400
  - HTTP 402
  - HTTP 404
  - quota exceeded / insufficient quota
  - billing / payment required
- 被标记为不可用的通道后续不会继续参与候选。
- 如果某个通道后续请求成功，会重新标记为可用。

## 左侧 API 状态

- 左侧侧边栏底部显示 API 状态。
- 只显示当前所选功能会用到的 API。
- 显示每组 API 已配置通道数量。
- 如果某个通道有测试或运行时状态，显示具体通道号：
  - 可用 `#1`
  - 失败 `#2`
  - 不可用 `#3`
  - 冷却 `#4`
- 400/404/402/billing/quota 会显示为不可用通道。
- 429/rate limit 临时限流会显示为冷却通道，不混到不可用里。
- 普通 API 失败会显示为失败通道，不会误标成长期不可用。
- 翻译/OCR/上色/渲染运行过程中更新的状态，和 API 管理页测试按钮更新的是同一套状态。
- 状态会定时刷新。
- 状态文案已接入 i18n，不应该再有硬编码中文。

## `.env` 和预设

- API 轮询配置仍保存在 `.env`。
- API 预设保存时要包含：
  - 原有 API key/model/base。
  - `_2/_3/...` 后缀通道。
  - 每组 API 的轮询策略。
- 加载预设后，API 管理页要恢复对应通道值和策略。
- 启动任务前的 API Key 校验要识别 `_2/_3/...` 通道。
- 只填第二个或第三个 key，也应算已配置。

## fallback 行为

- OCR/上色/渲染的专用 key 为空时，可以复用全局 key/base：
  - OpenAI 复用 `OPENAI_API_KEY` / `OPENAI_API_BASE`
  - Gemini 复用 `GEMINI_API_KEY` / `GEMINI_API_BASE`
- 上色和渲染不会复用全局翻译模型名，避免把翻译模型误用于图片生成。
- OpenAI 本地或自定义兼容接口仍允许空 key。

## i18n 行为

- 新增 UI 文案都必须走 `_t(...)`。
- 用户指出的这类硬编码不应存在：
  - `self.sidebar_api_status_title.setText("API 状态")`
- 已覆盖语言：
  - 简体中文
  - 繁体中文
  - 英文
  - 日文
  - 韩文
  - 西班牙文

## 明天重点验收

- 切换不同翻译器/OCR/上色器/渲染器后，API 管理页显示是否同步。
- 每组 API 默认是否为 3 个通道。
- 点击 `+` 后新增通道是否正常保存到 `.env`。
- 只填 `*_API_KEY_2` 时，启动校验是否通过。
- `failover` 是否每次请求都从第一个可用通道重新开始。
- 429/rate limit 后左侧状态是否显示冷却，不应显示为长期不可用。
- 400/404/402/billing/quota 后左侧状态是否显示不可用。
- 切换语言后，侧边栏 API 状态和 API 管理页是否没有硬编码中文。
- 预设保存/加载后，通道和策略是否恢复。
- Web 端页面是否没有变化。

## 已跑过的检查

- 目标 Python 文件 `py_compile` 通过。
- 6 个语言 JSON 解析通过。
- `git diff --check` 通过，只有 CRLF 提示。
- 做过以下 smoke：
  - slot 1 空、slot 2 有 key 时能解析出 slot 2。
  - 429 会把对应通道标记为 cooldown。
  - 空内容会在当前 key 内按重试次数重试，耗尽后切到 slot 2。
  - HTTP 400 会直接把当前通道标记为 unavailable，并切到 slot 2。
  - HTTP 404 会直接把当前通道标记为 unavailable，并切到 slot 2。
  - HTTP 402 会直接把当前通道标记为 unavailable，并切到 slot 2。
  - runtime override 只覆盖 model 时仍能使用 `.env` 里的 key。
