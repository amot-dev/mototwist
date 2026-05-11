export default {
  title: 'MotoTwist Docs',
  description: 'Documentation for MotoTwist',
  head: [
    ['link', { rel: 'icon', href: 'public/favicon.ico' }],
  ],
  lang: 'en-CA',
  ignoreDeadLinks: true,
  themeConfig: {
    nav: [
      { text: 'User Guide', link: '/user' },
      { text: 'Installation Guide', link: '/install' },
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/amot-dev/mototwist' },
    ],
    sidebar: {
      '/user': [
        {
          text: '⬅ Back',
          link: '/',
        },
      ],
      '/install': [
        {
          text: '⬅ Back',
          link: '/',
        },
        {
          text: 'Installation Guide',
          link: '/install',
          items: [
            { text: 'Environment Variables', link: '/install/env.md' },
            { text: 'Considerations', link: '/install/considerations.md' },
          ],
        },
      ],
    },
    lastUpdated: {
      text: 'Updated on',
      formatOptions: {
        dateStyle: 'long'
      },
    },
    footer: {
      copyright: 'Copyright © 2026-present Alexander Mot'
    },
  },
}
