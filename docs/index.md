---
layout: home

hero:
    name: MotoTwist
    text: Track the Thrill. Rate the Road.
    tagline: Share your favorite roads with a community of fellow riders and find your next great adventure, recommended by those who've ridden it before.
    image:
      src: /logo.png

features:
  - title: User Guide
    icon: 📑
    details: Making use of MotoTwist's features
    link: /user
  - title: Installation Guide
    icon: ⚙️
    details: Installing and configuring MotoTwist
    link: /install
  - title: Web App
    icon: 🏍
    details: Coming soon (Maybe)
    link: /coming-maybe.md
---

<div class="custom-section">
  <p class="custom-text">
    MotoTwist is the ultimate companion for every motorcycle enthusiast. Discover, track, and save your most epic journeys. MotoTwist allows you to define and rate motorcycle roads, both paved and unpaved, on various criteria. Weather conditions at the time of ride are also recorded: maybe a rainy day ruined a certain ride, but it's amazing in the sun! MotoTwist has support for multiple users, advanced filters help anyone find the exact road for them and the current conditions, and an ability to export it all to GPX and take it with you.
  </p>

  <img src="/screenshot_main.png" alt="A screenshot of MotoTwist, featuring the main view with a Twist popup open" class="custom-image" />
</div>

<script setup>
import { VPTeamMembers } from 'vitepress/theme'

const members = [
  {
    avatar: 'https://www.github.com/amot-dev.png',
    name: 'Alexander Mot',
    title: 'Creator',
    links: [
      { icon: 'github', link: 'https://github.com/amot-dev' },
    ]
  },
]
</script>
<VPTeamMembers size="small" :members style="display: flex; justify-content: center;"/>
