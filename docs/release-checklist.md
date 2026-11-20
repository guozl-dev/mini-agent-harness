# 发布前检查清单（脱敏与安全）

每次 push 到公开仓库前，按顺序过一遍。全部为只读命令，复制即可执行。

## 1. 密钥与凭证（最高优先级）

```bash
# 常见密钥形态：GitHub token / 模型 API key / 云厂商 AK / Slack token
git grep -nE "gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-" -- .
```

- [ ] 无真实密钥命中（`.env.example` 里的 `sk-xxxxxxxx` 占位符属正常）
- [ ] `.env` 从未被提交：`git log --all --oneline -- .env` 应输出为空
- [ ] 确认 `.gitignore` 含 `.env`

## 2. 个人信息

```bash
git grep -nE "手机号|身份证|学号|真实姓名|@(qq|163|gmail)\.com" -- .
```

- [ ] 无手机号、身份证、学号、私人邮箱
- [ ] 无真实公司名 / 客户名 / 未公开项目名
- [ ] 截图或文档中无个人信息（打码后再放入 `docs/assets/`）

## 3. 本机痕迹

```bash
git grep -nE "C:\\\\Users|/Users/|/home/|E:\\\\|D:\\\\" -- .
```

- [ ] 无绝对路径、无本机用户名
- [ ] 代码中路径均通过 `Path(__file__)` 或相对路径推导

## 4. 运行产物与大文件

```bash
git ls-files | grep -iE "\.sqlite|\.db$|\.log$|__pycache__|\.venv|\.zip$|\.mp4$"
git ls-files -s | awk '{print $4}' | xargs -I{} du -k "{}" 2>/dev/null | sort -rn | head -5
```

- [ ] 无数据库、日志、虚拟环境、缓存
- [ ] 单个文件 < 5 MB（GIF 演示建议 < 10 MB，优先用外链或压缩）

## 5. 提交者信息

```bash
git log --format="%h | %an | %ae" | head -10
```

- [ ] 邮箱为 GitHub 隐私地址（`*.users.noreply.github.com`）
- [ ] 提交者姓名按需选择：求职场景可用真名增强可信度；否则改为昵称

## 6. 许可证与来源

- [ ] `LICENSE` 存在且与预期一致（本项目 MIT）
- [ ] 引用的第三方代码/数据集已注明来源与许可

## 7. 自动化防护（本仓库已启用）

- [ ] `.github/workflows/secret-scan.yml`：每次 push/PR 用 gitleaks 扫描历史与变更
- [ ] `.github/workflows/ci.yml`：lint + 测试 + 覆盖率门槛
- [ ] 如出现误报，在仓库 **Security → Secret scanning** 里 Dismiss 并写明原因

## 8. 万一泄露了

1. **立即吊销并轮换**该密钥（删 commit 无效，历史中仍可检出）；
2. 使用 `git filter-repo` 或联系 GitHub Support 清理历史；
3. 检查平台账单与调用日志，确认无异常使用。
