#!/usr/bin/env node
// UserPromptSubmit hook: 理论推导类需求自动触发理论引擎。
// prompt 命中「理论推导/证明/可行性/为什么该 work/推导对不对」等 → 注入提醒：派 theorist + 跑 /theory-audit + 三层防线。
// 静默除非命中。仿 drift_guard.js 结构。

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', c => { input += c; });
process.stdin.on('end', () => {
  let data;
  try { data = JSON.parse(input); } catch (e) { process.exit(0); }
  const cwd = (data.cwd || '').replace(/\\/g, '/');
  if (!cwd.includes('YJ-Agent')) process.exit(0);

  const prompt = String(data.prompt || '');
  let out = '';

  const theoryish = /(理论推导|理论支撑|理论上|从理论|理论依据|理论保证|证明这|证明一下|证明它|可行性论证|可证伪|证伪|机理|机制上|为什么.{0,6}(work|有效|成立|该|能|可行|起作用)|推导.{0,4}(对|错|有没有问题|站得住)|理论塌|假设.{0,4}成立|回报.{0,4}(预测|保证)|该不该\s*work|理论上(能不能|该不该|会不会))/i.test(prompt);

  if (theoryish) {
    out += '[理论引擎] 命中理论推导类需求 → 派 theorist(opus) 做半形式化推导，跑 /theory-audit <project> [kickoff|diagnose|selfcheck]。三层防线：theorist 推导(逐步标假设+置信+来源) → skeptic 独立证伪(CoVe 式，命门多路投票) → verifier 核 csv 数。结论分档(定理/toy验/待跑)禁越级卖，文献空白标 TODO 不臆想，命门塌缩停下报拍板。\n';
  }

  if (out) process.stdout.write(out);
  process.exit(0);
});
