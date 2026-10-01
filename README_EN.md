# sansheng-stylebook

**Choose one visual style and keep it across a set of static images.** This Agent skill plans illustrations from source content, compiles style and palette rules, generates images through an available image tool, and checks each result. Article covers and illustrations are its first use case. Slide images, cards, infographics, stories, comics, audio covers, and stickers are at varying trial stages. [中文说明](./README.md)

> Public beta. All 72 public styles have callable contracts, each crediting its inspiration (artists, studios, works) and shipping same-topic sample images. After the 2026-09-30 library rebuild every style is pending admission under its new revision (five had passed the older matrix on earlier revisions and need re-testing). A passing style test does not approve every subject or complete format. The official website selector and integration into `sansheng-write` are still pending.

## Preview

| Style | Real single-image test output |
|---|---|
| C01 warm hand-painted animation | ![C01 story image](./assets/C01-story-sample.png) |
| C32 aged-paper technical briefing | ![C32 infographic](./assets/C32-infographic-sample.png) |

These images show two separate successful tests, not a validated cross-format series. File hashes and known generation routes are documented in [ASSET_PROVENANCE.md](./ASSET_PROVENANCE.md).

## How decisions are made

1. Read the task and source text; extract evidence, relationships, and only the short labels needed in an image.
2. Select one style for the series. An explicit choice wins over a project lock, saved preference, or factory default. Palette changes must respect each style's recoloring rule.
3. Choose a scene, flow, comparison, or other structure **per image** according to its content. A preference for character art must not turn a numerical comparison into an unrelated portrait.
4. Compile, generate, and inspect the actual output. Failed or repaired images remain in the record and do not automatically count as style admission.

Temporary edits affect only the current task. Explicit long-term preferences live in a local file and can be viewed, undone, or forgotten. Observed preferences only improve ranking after consistent active choices in three independent tasks; silence and automatic scores are not used to infer taste.

## Install and try

Python 3.10+ is required. Clone the repository and link it into your Agent's skill directory. The repository also includes a Claude Code plugin manifest:

```bash
git clone https://github.com/sanshengai/sansheng-stylebook.git
cd sansheng-stylebook
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 scripts/sb.py doctor
python3 scripts/sb.py compile examples/quickstart/manifest.json --json
```

Contributors should run `git config core.hooksPath .githooks` to enable the staged-file redaction guard.

For an Agent with a built-in image generator, pass the full compiled `prompt` and any listed references to that tool. For an external image provider, configure credentials locally with `python3 scripts/sb.py setup --env-template` and then:

```bash
python3 scripts/sb.py setup
python3 scripts/sb.py generate examples/quickstart/manifest.json -o /tmp/stylebook-first.png
python3 scripts/sb.py qa /tmp/stylebook-first.png --style C32 --manifest examples/quickstart/manifest.json
```

The QA command requires a working independent vision reviewer, or a separately supplied review record. A missing reviewer is not a passing result. If no generator is configured, `python3 scripts/sb.py inbox examples/quickstart/manifest.json -d /tmp/stylebook-inbox` makes a portable prompt package. `doctor --deep` makes real provider calls and may incur charges. PPTX assembly needs the optional `requirements-ppt.txt` dependencies.

## Choose and adjust

- `python3 scripts/sb.py style-for wxillus` shows the article illustration default and why it was selected.
- `python3 scripts/sb.py build --gallery` creates the offline selector at `gallery/build/index.html`. It exports versioned selection JSON that the Agent can parse. The public selector is live at https://sanshengai.top/tools/stylebook/ (pick a use, a style and a palette, then copy one `sb2:` line for the Agent). Serve `gallery/build/` over a local static server to use the same page offline (`img/` holds lazily loaded samples); `--advanced` builds the old all-in-one gallery.
- `python3 scripts/sb.py preferences set --scene wxillus --field style --value C01` saves a style preference. See [preference controls](./references/preferences.md).
- For an article, create a source-grounded plan and run `sb.py plan` before generating. See [planning rules](./references/planning.md) and the [synthetic plan](./examples/content-plan-v2/plan.json); its C31 style remains pending admission.

Private styles and personal memory are excluded from the public package. Local memory defaults to `~/.config/sansheng-stylebook/profile/` and can be relocated with `STYLEBOOK_PROFILE`. Provider support and its verified limits are listed in [backends.md](./references/backends.md).

## Credits and license

See [CHANGELOG.md](./CHANGELOG.md), [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md), and [MIT LICENSE](./LICENSE). Style and workflow ideas were adapted from [threerocks/hand-drawn-styles](https://github.com/threerocks/hand-drawn-styles), [JimLiu/baoyu-skills](https://github.com/JimLiu/baoyu-skills), and [yang0/handraw-style](https://github.com/yang0/handraw-style). Maintained by 叁笙 (sansheng).
