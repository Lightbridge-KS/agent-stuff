# Credits

Owned runtime initially scaffolded with `create-vite` 9.3.1's React/TypeScript
starter, then replaced with the fixed document compiler, kit, and isolated viewer.

The exact package catalog and transitive versions are recorded in
`runtime/package.json` and `runtime/pnpm-lock.yaml`. Runtime code bundles React,
React DOM, Scheduler, and generated Ajv validation helpers. Their license notices
are preserved in `runtime/THIRD-PARTY-NOTICES.txt` and copied into rendered exports.
MDX, remark-gfm, Vite, TypeScript, Biome, Playwright, and axe-core are build/check tools;
no installed dependency directories are distributed in the skill.

The visual direction was derived from user-supplied ChatGPT Intelligent UI
screenshots. No screenshots, ChatGPT assets, fonts, or proprietary source are shipped.
