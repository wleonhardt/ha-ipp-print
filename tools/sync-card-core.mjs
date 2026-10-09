// Development-only synchronization; released cards are already complete single files.
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const root = new URL('../', import.meta.url);
const domain = readdirSync(new URL('custom_components/', root)).find(name => !name.startsWith('_') && name !== '.DS_Store');
const target = new URL(`custom_components/${domain}/static/card.js`, root);
const canonical = readFileSync(new URL('shared/card-core.js', root), 'utf8').trimEnd();
const source = readFileSync(target, 'utf8');
const block = /\/\/ BEGIN DOCUMENT CARD CORE v\d+[\s\S]*?\/\/ END DOCUMENT CARD CORE v\d+/;
const found = source.match(block);
if (!found) throw new Error(`Missing core markers: ${fileURLToPath(target)}`);
if (process.argv.includes('--write')) writeFileSync(target, source.replace(block, () => canonical));
else if (found[0] !== canonical) throw new Error('Card core drift: run node tools/sync-card-core.mjs --write');
else console.log('Document card core v3 matches its vendored source.');
