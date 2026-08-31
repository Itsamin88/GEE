#!/usr/bin/env node
/**
 * Builds THE_SIMPLIFIED_PLAN_v4.0.docx from plan_content_1..4.js.
 *
 * The original THE_SIMPLIFIED_PLAN_v3.8.docx is never opened for writing and
 * never modified; it is preserved in originals/.
 */
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageOrientation, PageBreak, TableOfContents, Footer, PageNumber,
  LevelFormat, convertInchesToTwip,
} = require('docx');

const OUT = path.join(__dirname, '..', 'THE_SIMPLIFIED_PLAN_v4.0.docx');

const content = [].concat(
  require('./plan_content_1.js'),
  require('./plan_content_2.js'),
  require('./plan_content_3.js'),
  require('./plan_content_4.js'),
);

// --- page geometry: A4 portrait, 1" margins -------------------------------
const PAGE_W = 11906;                 // A4 width in DXA
const MARGIN = 1080;                  // 0.75"
const CONTENT_W = PAGE_W - 2 * MARGIN; // 9746

const NAVY = '1F3B4D';
const SLATE = '4A5D6B';
const RULE = 'C8D4DC';
const HDRFILL = '1F3B4D';
const BOXFILL = 'F2F6F9';
const ALTFILL = 'F7FAFC';

function txt(s, opts = {}) { return new TextRun({ text: String(s), ...opts }); }

/** Split a cell string on ALL-CAPS emphasis is overkill; instead bold a leading
 *  ALL-CAPS clause up to the first period, which is how the source text signals
 *  emphasis. Everything else renders plain. */
function cellRuns(s, { bold = false, size = 17 } = {}) {
  const str = String(s == null ? '' : s);
  const m = str.match(/^([A-Z][A-Z0-9 ,'’\-–—()/.]{9,}?)([.:]\s|\s—\s|$)/);
  if (m && m[1].length < str.length) {
    return [
      txt(m[1], { bold: true, size, color: NAVY }),
      txt(str.slice(m[1].length), { bold, size }),
    ];
  }
  return [txt(str, { bold, size })];
}

function para(text, opts = {}) {
  const { size = 19, bold = false, italics = false, color, align, spacingBefore = 0,
          spacingAfter = 120, indent, font } = opts;
  return new Paragraph({
    alignment: align,
    spacing: { before: spacingBefore, after: spacingAfter, line: 264 },
    indent,
    children: [new TextRun({ text: String(text), size, bold, italics, color, font })],
  });
}

function cell(children, { width, fill, header = false, colSpan } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    columnSpan: colSpan,
    shading: fill ? { type: ShadingType.CLEAR, fill, color: 'auto' } : undefined,
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    children,
  });
}

/** Column widths: give the widest columns more room, in DXA summing to CONTENT_W. */
function computeWidths(header, rows) {
  const n = (header ? header.length : rows[0].length);
  const score = new Array(n).fill(0);
  const all = (header ? [header] : []).concat(rows);
  for (const r of all) {
    for (let i = 0; i < n; i++) {
      const len = String(r[i] == null ? '' : r[i]).length;
      score[i] = Math.max(score[i], Math.min(len, 320));
    }
  }
  // soften: sqrt keeps a 400-char cell from starving a 6-char one
  const soft = score.map(s => Math.sqrt(Math.max(s, 3)));
  const total = soft.reduce((a, b) => a + b, 0);
  const minW = 520;
  let w = soft.map(s => Math.max(minW, Math.round(CONTENT_W * s / total)));
  // normalise so the widths sum exactly to CONTENT_W
  const diff = CONTENT_W - w.reduce((a, b) => a + b, 0);
  const iMax = w.indexOf(Math.max(...w));
  w[iMax] += diff;
  return w;
}

function table(header, rows) {
  const widths = computeWidths(header, rows);
  const trs = [];
  const hasHeader = header && header.some(h => String(h).trim() !== '');
  if (hasHeader) {
    trs.push(new TableRow({
      tableHeader: true,
      children: header.map((h, i) => cell(
        [new Paragraph({ spacing: { before: 20, after: 20 },
          children: [txt(h, { bold: true, size: 17, color: 'FFFFFF' })] })],
        { width: widths[i], fill: HDRFILL })),
    }));
  }
  rows.forEach((r, ri) => {
    trs.push(new TableRow({
      children: r.map((c, i) => cell(
        [new Paragraph({ spacing: { before: 20, after: 20 }, children: cellRuns(c) })],
        { width: widths[i], fill: (!hasHeader && i === 0) ? ALTFILL : (ri % 2 ? ALTFILL : undefined) })),
    }));
  });
  return new Table({
    columnWidths: widths,
    width: { size: CONTENT_W, type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      left: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      right: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      insideVertical: { style: BorderStyle.SINGLE, size: 4, color: RULE },
    },
    rows: trs,
  });
}

/** A callout box: a single shaded table, label above body. */
function box(rows) {
  const trs = [];
  for (const [label, body] of rows) {
    trs.push(new TableRow({
      children: [cell([
        new Paragraph({ spacing: { before: 40, after: 60 },
          children: [txt(label, { bold: true, size: 18, color: NAVY })] }),
        ...String(body).split(' / ').map((seg, i, arr) => new Paragraph({
          spacing: { before: 0, after: i === arr.length - 1 ? 40 : 80 },
          children: [txt(seg.trim(), { size: 18 })],
        })),
      ], { width: CONTENT_W, fill: BOXFILL })],
    }));
  }
  return new Table({
    columnWidths: [CONTENT_W],
    width: { size: CONTENT_W, type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 12, color: NAVY },
      bottom: { style: BorderStyle.SINGLE, size: 12, color: NAVY },
      left: { style: BorderStyle.NONE, size: 0, color: 'auto' },
      right: { style: BorderStyle.NONE, size: 0, color: 'auto' },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      insideVertical: { style: BorderStyle.NONE, size: 0, color: 'auto' },
    },
    rows: trs,
  });
}

// --- assemble -------------------------------------------------------------
const children = [];
let nTables = 0, nBoxes = 0, nHeadings = 0, nParas = 0, nLists = 0, nFormulas = 0;

for (const b of content) {
  switch (b.t) {
    case 'TITLE':
      children.push(new Paragraph({
        alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 },
        children: [txt(b.text, { bold: true, size: 22, color: SLATE })] }));
      break;
    case 'SUBTITLE':
      children.push(new Paragraph({
        alignment: AlignmentType.CENTER, spacing: { before: 0, after: 100 },
        children: [txt(b.text, { bold: true, size: 40, color: NAVY })] }));
      break;
    case 'SUBTITLE2':
      children.push(new Paragraph({
        alignment: AlignmentType.CENTER, spacing: { before: 0, after: 80 },
        children: [txt(b.text, { size: 20, color: SLATE })] }));
      break;
    case 'VERSION':
      children.push(new Paragraph({
        alignment: AlignmentType.CENTER, spacing: { before: 120, after: 300 },
        border: { top: { style: BorderStyle.SINGLE, size: 6, color: NAVY },
                  bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY } },
        children: [txt(b.text, { size: 18, italics: true, color: SLATE })] }));
      break;
    case 'H1':
      nHeadings++;
      children.push(new Paragraph({ children: [new PageBreak()] }));
      children.push(new Paragraph({
        heading: HeadingLevel.HEADING_1,
        spacing: { before: 0, after: 200 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: NAVY } },
        children: [txt(b.text, { bold: true, size: 32, color: NAVY })] }));
      break;
    case 'H2':
      nHeadings++;
      children.push(new Paragraph({
        heading: HeadingLevel.HEADING_2,
        spacing: { before: 320, after: 140 },
        children: [txt(b.text, { bold: true, size: 24, color: NAVY })] }));
      break;
    case 'H3':
      nHeadings++;
      children.push(new Paragraph({
        heading: HeadingLevel.HEADING_3,
        spacing: { before: 240, after: 110 },
        children: [txt(b.text, { bold: true, size: 20, color: SLATE })] }));
      break;
    case 'P':
      nParas++;
      children.push(new Paragraph({
        spacing: { before: 0, after: 140, line: 268 },
        children: cellRuns(b.text, { size: 19 }) }));
      break;
    case 'FORMULA':
      nFormulas++;
      children.push(new Paragraph({
        spacing: { before: 30, after: 30 },
        indent: { left: convertInchesToTwip(0.3) },
        children: [txt(b.text, { size: 18, font: 'Consolas', color: NAVY })] }));
      break;
    case 'BUL':
      nLists++;
      b.items.forEach(it => children.push(new Paragraph({
        bullet: { level: 0 },
        spacing: { before: 40, after: 60, line: 264 },
        children: cellRuns(it, { size: 19 }) })));
      break;
    case 'NUM':
      nLists++;
      b.items.forEach(it => children.push(new Paragraph({
        numbering: { reference: 'plan-numbers', level: 0, instance: nLists },
        spacing: { before: 40, after: 60, line: 264 },
        children: cellRuns(it, { size: 19 }) })));
      break;
    case 'TBL':
      nTables++;
      children.push(table(b.header, b.rows));
      children.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
      break;
    case 'BOX':
      nBoxes++;
      children.push(box(b.rows));
      children.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
      break;
    default:
      throw new Error('unknown block type: ' + b.t);
  }
}

const doc = new Document({
  creator: 'Study 1 implementation plan',
  title: 'The Simplified Plan v4.0',
  description: 'Implementation plan for Study 1 after the removal of documentary practice codes',
  numbering: {
    config: [{
      reference: 'plan-numbers',
      levels: [{
        level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.START,
        style: { paragraph: { indent: { left: 460, hanging: 300 } } },
      }],
    }],
  },
  styles: {
    default: {
      document: { run: { font: 'Calibri', size: 19 } },
    },
  },
  sections: [{
    properties: {
      page: {
        size: { width: PAGE_W, height: 16838, orientation: PageOrientation.PORTRAIT },
        margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN },
      },
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [txt('The Simplified Plan v4.0   ·   ', { size: 15, color: SLATE }),
                     new TextRun({ children: [PageNumber.CURRENT], size: 15, color: SLATE })],
        })],
      }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log('wrote', OUT, (buf.length / 1024).toFixed(0) + ' KB');
  console.log(`blocks=${content.length}  headings=${nHeadings}  paragraphs=${nParas}  ` +
              `tables=${nTables}  boxes=${nBoxes}  lists=${nLists}  formulas=${nFormulas}`);
});
