# Bio Research Tools

面向 Codex CLI 的仓库级生物医学文献综述工具。目前只包含一个技能：
`literature-review`。

该技能组合使用：

- PubMed MCP：检索论文、获取 PMID 元数据、查找相关论文
- Crossref helper：校验 DOI 和撤稿信息
- OpenAlex helper：补充检索并扩展前向、后向引用

## 当前范围

当前为 Linux P0 版本，仅支持 `linux-64`。PubMed MCP 只暴露三个只读工具：

- `search_articles`
- `get_article_metadata`
- `find_related_articles`

原始 runtime 发布包不参与运行，也不会被修改。

## 前置条件

- [Codex CLI](https://developers.openai.com/codex/cli)
- [Pixi](https://pixi.prefix.dev/)
- Git

## 安装

```bash
git clone https://github.com/lantian1986/bio_research_tools.git
cd bio_research_tools
pixi install --locked
```

从仓库根目录启动 Codex，并在提示时信任该仓库：

```bash
codex
```

Codex 会自动读取：

- `.agents/skills/literature-review/SKILL.md`
- `.codex/config.toml`

可在 Codex 中检查：

```text
/skills
/mcp
```

## 使用

显式调用技能：

```text
$literature-review：综述近五年 CRISPR 体内基因编辑的临床证据。
```

其他示例：

```text
$literature-review：哪篇论文首次报道了某项技术？请核验 DOI。

$literature-review：比较方法 A 和方法 B 的证据、局限和适用场景。

$literature-review：根据这些 PMID 总结一致结论、争议和研究空白。
```

## 可选环境变量

```bash
export NCBI_EMAIL="you@example.com"
export NCBI_API_KEY="..."
export LITERATURE_REVIEW_EMAIL="you@example.com"
```

- `NCBI_EMAIL`：随 PubMed E-utilities 请求发送的联系邮箱
- `NCBI_API_KEY`：提高 NCBI API 允许的请求频率
- `LITERATURE_REVIEW_EMAIL`：用于 Crossref/OpenAlex polite-pool 请求

不要将密钥写入 `.codex/config.toml`、`pixi.toml` 或 Git。

## 开发与验证

安装锁定环境：

```bash
pixi install --locked
```

运行测试：

```bash
pixi run --frozen test
```

执行 Python 静态编译检查：

```bash
pixi run --frozen check
```

手动启动 PubMed MCP：

```bash
pixi run --frozen pubmed-mcp
```

调用文献 helper：

```bash
pixi run --frozen literature-helper verify-dois request.json
pixi run --frozen literature-helper search-openalex request.json
pixi run --frozen literature-helper expand-citations request.json
```

helper 接受带有 `"version": 1` 的 JSON 对象，结果写入 stdout，诊断信息写入
stderr。具体请求格式见技能文件。

## 目录

```text
.agents/skills/literature-review/  Codex 技能与 helper
.codex/config.toml                 项目级 MCP 配置
mcp-servers/pubmed/                三工具 PubMed MCP
tests/                             单元与结构测试
pixi.toml / pixi.lock              可复现运行环境
```

## 数据与许可

查询和论文标识符会发送到 PubMed、Crossref 或 OpenAlex。使用前请确认符合相应
服务的条款、隐私政策和速率限制。详细信息见
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

本项目使用 [Apache License 2.0](LICENSE)。
