// @ts-check

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: "Vintex — Back-end",
  tagline: "Documentacao viva do back-end (VE-25)",
  favicon: "img/favicon.ico",

  url: "https://vintex-ages.github.io",
  baseUrl: "/back-end/",

  organizationName: "Vintex-Ages",
  projectName: "back-end",

  onBrokenLinks: "throw",
  markdown: {
    hooks: {
      onBrokenMarkdownLinks: "warn",
    },
  },

  i18n: {
    defaultLocale: "pt-BR",
    locales: ["pt-BR"],
  },

  presets: [
    [
      "classic",
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          routeBasePath: "/",
          sidebarPath: require.resolve("./sidebars.js"),
          editUrl: "https://github.com/Vintex-Ages/back-end/tree/develop/documentation/",
        },
        blog: false,
        theme: {
          customCss: require.resolve("./src/css/custom.css"),
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      navbar: {
        title: "Vintex — Back-end",
        items: [
          {
            href: "https://github.com/Vintex-Ages/back-end",
            label: "GitHub",
            position: "right",
          },
        ],
      },
      footer: {
        style: "dark",
        copyright: `Vintex — gerado a partir de documentation/ no back-end.`,
      },
    }),
};

module.exports = config;
