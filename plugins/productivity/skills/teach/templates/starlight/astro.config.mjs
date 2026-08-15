// @ts-check
// Starlight config for a /teach workspace.
// Fill every {placeholder}; delete comments once settled.
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid';

// https://astro.build/config
export default defineConfig({
	integrations: [
		starlight({
			title: '{Course title — evocative, not the topic name}',
			customCss: ['./src/styles/teach.css'],
			// Tier-1 quiz widget, loaded on every page. Authoring contract is
			// documented in public/quiz.js.
			head: [
				{
					tag: 'script',
					attrs: { src: '/quiz.js', defer: true },
				},
			],
			// The sidebar IS the visible syllabus — edited each session as lessons
			// land. Groups = parts, added as the syllabus takes shape. Starlight
			// >= 0.39 requires nested groups to wrap content in `items:`.
			sidebar: [
				{ label: 'Preface', link: '/' },
				// {
				// 	label: 'I — {Arc title}',
				// 	items: [
				// 		{ label: '{Lesson label}', slug: 'lessons/01-{slug}' },
				// 	],
				// },
				{ label: 'Review', slug: 'review' },
			],
		}),
		mermaid({
			theme: 'forest',
			autoTheme: true,
		}),
	],
});
