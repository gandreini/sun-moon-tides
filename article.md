# Tales of AI: Building Sun Moon Tides, a tidal service from 0 to 1

Titles:

- Building a tide engine without knowing the science (miracles of AI)
- Tales of AI: Building Sun Moon Tides, a tidal service from 0 to 1

Mondo is a side project I've been running for more than five years. It's a surf atlas and forecasting app covering 5,500+ surf spots worldwide. For each spot it provides the exact location on a map, wave info, sun and moon data, tides, surf forecast, and a bunch of other info. Over the years I learned enough frontend and backend development to ship and maintain it, and it has grown into six separate <u>components</u> plus a bunch of [n8n](https://n8n.io/) automations.

The scientific data (astronomy, tides, forecast) has always been a black box I paid external services to handle as I assumed this stuff was too complex for me to touch.

But one of my goals for 2026 was to drastically cut Mondo's maintenance costs, so I started questioning my dependence on all the external services I'm using, including those for tide and forecast data. The wave forecast engine is very complex (atmospheric modeling, swell propagation, bathymetry) and I found a good cheap alternative in [Open-Meteo](https://open-meteo.com/) for that. But tides? The moon and sun pull the ocean in predictable patterns. People have been calculating this since the 1700s. How hard could it actually be?

The honest answer a year ago would have been *"I have no idea how to do it"*, I'm a product designer, not an oceanographer (I have a master degree in Geology but that's another story!). But the push to reduce costs + some part of my brain that thinks everything is possible +  the curiosity to explore how far I could go with AI, pushed me to start investigating.

## Starting the conversation

Having no idea of the feasibility of the project, I just started asking [Claude](https://claude.ai/):

> *Hey dude for my project Mondo I want to create a minimal tide application
1. Should be capable of returning the 7 days tide forecast for any lat and long
2. Should return the highs and lows and corresponding time and size
3. Should expose the data on an endpoint API
4. Should be build as much as possible with n8n

I spent some time in conversation going back and forth with Claude which was <u>alternating exitement about the project with extreme optimism, with moments of pessimism</u>, saying it was not possible and I had to pay for a service. But I kept pushing.  He metioned FES2022, a global ocean tide model from French oceanographic research, containing raw tidal constituent data for the entire planet. I started insisting on that direction going deeper to understand the feasibility. By the end of that first conversation, I had a clear picture: this was doable. The direction was FES2022, so I requested access to the dataset.

## From exploration to brief to working code

After I got access to FES2022, I started a second conversation with Claude to <u>move to the actual building of the project:</u>

> *"Hi I'd like to build a custom tide service for my project Mondo, here are the guidelines:
1. Should expose tide data through an API endpoint
2. Should be installed on a docker on my Digital Ocean server
3. Can be built with Python or any other tech I can install there
4. Should make use of FES 20225.
5. Should receive lat and long of any surf spot near the coast and return the 14 days tide with highs and lows (for each should provide the date time, and size)
I upload the manual of FES 2022 can you have a look and tell me how to proceed?"*

After that conversation we mapped out the architecture, I asked Claude to write me the initial prompt to give to [Claude Code](https://docs.anthropic.com/en/docs/claude-code), a detailed brief with all the context and decisions made. Then I moved to Claude Code and the actual coding started.

Ten days, a few hours each day around my full-time job at [n8n](https://n8n.io/). I didn't write a line of code myself, I spent that time guiding Claude Code, discussing and sharing decisions, giving prompts, and iterating when something wasn't right. Claude Code handled the stack: [FastAPI](https://fastapi.tiangolo.com/), [NetCDF](https://www.unidata.ucar.edu/software/netcdf/) scientific data parsing, harmonic analysis math, the API layer. When things were wrong, I described problems like: *"the high tide peaks are offset by about 1 hour from the reference data, can you check why and fix it?"*.

A few days after I started, the application was live, fully integrated with Mondo, providing the tide and astronomy data for all the surf spots. I named the  project "Sun Moon Tides" and I released it as open source on GitHub.

## Trust the black box

Here's the thing about building in a domain you don't fully understand with a coding language you don't know (Python in this case): you can't review the code or look at harmonic analysis equations and spot an error. So the way to understand if the thing you built works as expected is to test and check results.

First, I kept pushing Claude Code to write as many automated tests as possible. The project ended up with 85 tests across three test suites, covering everything from the harmonic math to the API responses. I provided an array of coastal locations spread across different oceans and coastlines around the world so the tests would verify the engine worked globally.

Then I asked to build a visual comparison dashboard. It fetches predictions from [NOAA](https://tidesandcurrents.noaa.gov/) (the gold standard for US waters), [Stormglass](https://stormglass.io/), and [WorldTides](https://www.worldtides.info/), then overlays my FES2022-based predictions alongside them. Same coordinates, same time range, direct visual comparison. Being able to eyeball the results across multiple providers gave me the confidence that unit tests alone couldn't.

Two findings surprised me. My self-hosted engine was genuinely accurate, actually competitive with the paid services. And I also discovered that the paid services often disagree with each other. I found meaningful variances in timing and height between providers for the same locations. Tides are complex, can be calculated in different ways, and some providers mix sicentific data a with empirical observation. My engine fits comfortably within that range of variance. At every update, I kept going back to the dashboard to make sure things stayed on the right track.

## What this is really about

A year ago, I wouldn't have even spent time on this. Oceanographic physics, scientific data formats, harmonic analysis is domain knowledge I simply didn't have. But nowdays, it was worth trying, and it took a few hours of work spread across ten days to go from *"this is impossible"* to a working engine integrated into Mondo, and working on it was fun.

What also shifted is the way the work itself happens. Instead of spending most of the time writing code, the code is written by agents. The real time goes into evaluating results, asking agents to write tests, and building applications to verify the output is correct.

What I didn't expect is that AI didn't just help with the coding. It helped me understand the science. Through conversation, I built a mental model of how tidal prediction actually works. The tools didn't just write Python for me. They made a whole domain accessible.

I later understood that this project happened at a crucial moment that's december 2025. During the Christmas holidays I started noticing as on X a lot of poeple started talking about how coding with agents <u>reached a next level</u>, and the fact that agents could write most of the code (which seemed some click bait title a few months ago) had become reality, mostly due to the release of Opus 4.5. These comments resonated with me as I experienced the same exact thing working on Sun Moon Tides.

## What's next?

This project confirmed me once again that we can do whatever we want with the just amount of commitment and excitement, juts go deep in the rabbit hole and sometimes results are there. The new thing this time was adding AI to the equation, which increased the possibilities even further and sped up the process by a lot. I don't knwo what's next, but I'm already exploring  other projects....

What a time to be alive, at least till we have a job!

## The project

[Sun Moon Tides](https://github.com/gandreini/sun-moon-tides) is open source. It's a REST API for global tide predictions and astronomy data, self-hosted, free, works for any coordinates on the planet. If you're running a project that needs tide or astronomy data without ongoing API costs, it might save you some money and some dependency. Fork it, improve it, use it.

*I'm a product designer at n8n with 20+ years in the industry. I build [Mondo](https://www.mondo.surf/) on the side and a few other projects. You can find me on [LinkedIn](https://linkedin.com).*

<!-- Tags: Product Design, AI, Side Projects, Open Source, Building In Public -->
