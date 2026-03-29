#!/usr/bin/env node
/**
 * publish.mjs
 * 
 * 在 Claude Code 环境中运行
 * 读取 output/articles/ 下待发布文章
 * 依次调用 baoyu-skills 完成：
 *   1. baoyu-format-markdown   → 格式规范化 + frontmatter
 *   2. baoyu-cover-image       → 生成封面图
 *   3. baoyu-article-illustrator → 文章内配图
 *   4. baoyu-post-to-wechat    → 发布公众号
 * 
 * 使用方式（在 Claude Code 中）：
 *   node scripts/publish.mjs
 *   或让 Claude Code 直接执行：
 *   "请读取 output/articles/ 下所有 .md 文件，依次用 baoyu-skills 配图并发到公众号"
 */

import { readdir, readFile, writeFile } from 'fs/promises';
import { join, basename } from 'path';

const ARTICLES_DIR = './output/articles';
const PUBLISHED_LOG = './output/published.json';

async function loadPublished() {
  try {
    return JSON.parse(await readFile(PUBLISHED_LOG, 'utf8'));
  } catch {
    return [];
  }
}

async function savePublished(list) {
  await writeFile(PUBLISHED_LOG, JSON.stringify(list, null, 2));
}

async function getPendingArticles() {
  const files = await readdir(ARTICLES_DIR);
  const published = await loadPublished();
  const publishedSet = new Set(published);

  return files
    .filter(f => f.endsWith('.md') && !publishedSet.has(f))
    .map(f => join(ARTICLES_DIR, f));
}

/**
 * 生成给 Claude Code 的指令
 * Claude Code 会按顺序执行这些 skill 命令
 */
function buildClaudeCodeInstructions(articlePath) {
  const filename = basename(articlePath);
  return `
请按以下步骤处理文章 ${articlePath}：

## 步骤 1：格式规范化
/baoyu-format-markdown ${articlePath}
等待完成，记录输出的格式化文件路径（通常是 *-formatted.md）。

## 步骤 2：生成封面图
对格式化后的文件执行：
/baoyu-cover-image [格式化文件路径] --type conceptual --palette cool --rendering digital --quick

## 步骤 3：文章内配图
/baoyu-article-illustrator [格式化文件路径] --style blueprint

## 步骤 4：发布到微信公众号
/baoyu-post-to-wechat 文章 --markdown [格式化文件路径]

## 完成后
在 output/published.json 中记录 "${filename}" 已发布。
`.trim();
}

// 主流程
async function main() {
  const pending = await getPendingArticles();

  if (pending.length === 0) {
    console.log('✅ 没有待发布文章');
    return;
  }

  console.log(`📝 找到 ${pending.length} 篇待发布文章：`);
  pending.forEach(p => console.log(`  - ${basename(p)}`));

  // 输出 Claude Code 指令（在 CI 中打印到 stdout，Claude Code 会读取并执行）
  for (const articlePath of pending) {
    console.log('\n' + '='.repeat(60));
    console.log(buildClaudeCodeInstructions(articlePath));
  }
}

main().catch(console.error);
