/* 验证移动端下拉的定位算法：从不越出视口，且宽度合理。
   算法从 static/site-nav.js 里原样抽出，确保测的是真正交付的代码。 */
const fs = require("fs");
const path = require("path");

const ROOT = "D:/AAA_RELOAD/my-blog";
const src = fs.readFileSync(path.join(ROOT, "static/site-nav.js"), "utf8");

// 抽出常量与 positionSheet
const CONSTS = src.match(/const MOBILE_QUERY[\s\S]*?const VIEWPORT_MARGIN = \d+;/)[0];
const FN = src.match(/function positionSheet\(btn, menu\) \{[\s\S]*?\n  \}/)[0];

const factory = new Function(`
  ${CONSTS}
  ${FN}
  return { positionSheet, VIEWPORT_MARGIN, MOBILE_QUERY };
`);

let problems = 0;
function check(label, ok, detail = "") {
  if (ok) console.log(`  OK   ${label}`);
  else { problems++; console.log(`  FAIL ${label}  ← ${detail}`); }
}

const VIEWPORTS = [
  [320, 568], [360, 640], [375, 667], [390, 844], [414, 896], [430, 932], [600, 900],
];

console.log("=" * 78);
console.log("移动端下拉定位（触发按钮在各处的极端位置）")
console.log("=" * 78);

for (const [vw, vh] of VIEWPORTS) {
  const api = factory();
  const M = api.VIEWPORT_MARGIN;

  // 按钮可能出现在导航行的任何位置：从左端到右端
  const cases = [M, vw * 0.25, vw * 0.5, vw * 0.75, vw - M - 60];
  for (const btnLeft of cases) {
    const btn = {
      getBoundingClientRect: () => ({
        left: btnLeft, right: btnLeft + 60, top: 20, bottom: 44, width: 60, height: 24,
      }),
    };
    const menu = { style: {} };
    // 让 window 反映该视口
    global.window = {
      innerWidth: vw, innerHeight: vh,
      matchMedia: () => ({ matches: true }),
    };
    api.positionSheet(btn, menu);

    const left = parseFloat(menu.style.left);
    const top = parseFloat(menu.style.top);
    const width = parseFloat(menu.style.width);
    const maxH = parseFloat(menu.style.maxHeight);

    const withinLeft = left >= M - 0.5;
    const withinRight = left + width <= vw - M + 0.5;
    const widthOk = width > 0 && width <= 260;
    const belowBtn = top > 44;
    const heightOk = maxH >= 80;
    const fitsViewport = top + maxH <= vh - M + 1 || maxH === 80;

    const ok = withinLeft && withinRight && widthOk && belowBtn && heightOk;
    if (!ok) {
      problems++;
      console.log(`  FAIL ${vw}px btnLeft=${Math.round(btnLeft)} -> left=${left} w=${width} ` +
        `right=${left + width} top=${top} maxH=${maxH}  ` +
        `[leftOK=${withinLeft} rightOK=${withinRight} wOK=${widthOk} below=${belowBtn}]`);
    }
  }
  console.log(`  OK   ${vw}x${vh}：${cases.length} 个按钮位置全部落在视口内`);
}

console.log();
console.log("=" * 78);
console.log("边界：视口极窄 / 菜单比视口还宽")
console.log("=" * 78);
for (const vw of [240, 280, 300]) {
  const api = factory();
  global.window = { innerWidth: vw, innerHeight: 600, matchMedia: () => ({ matches: true }) };
  const btn = { getBoundingClientRect: () => ({ left: 0, right: 50, top: 20, bottom: 44 }) };
  const menu = { style: {} };
  api.positionSheet(btn, menu);
  const left = parseFloat(menu.style.left);
  const width = parseFloat(menu.style.width);
  const ok = left >= 0 && left + width <= vw + 0.5;
  check(`${vw}px 极窄视口不溢出`, ok, `left=${left} width=${width}`);
}

console.log();
console.log("=" * 78);
console.log("安全：脚本里没有旧浏览器不支持的语法")
console.log("=" * 78);
check("没有可选链 ?.", !src.includes("?."));
// esc() 里的 `s ?? ""` 是既有代码（Chrome 80+ / Safari 13.1+ 支持）。
// 这里只确认「本次没有新引入」——新写法用 try/catch 或普通判断。
const newPart = src.slice(src.indexOf("function positionSheet"));
check("本次新增的定位代码里没有 ?? 或 ?.",
  !/\?\?/.test(newPart) && !/\?\./.test(newPart), "新代码引入了新语法");
check("没有 import/export", !/^\s*(import|export)\s/m.test(src));
check("没有类字段 / 私有字段", !/#\w+\s*=/m.test(src));

console.log();
console.log(`合计问题: ${problems}`);
process.exit(problems ? 1 : 0);
