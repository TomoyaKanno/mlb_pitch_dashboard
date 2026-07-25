---
title: MLB Pitch Workload
---

```js
const dashboard = FileAttachment("./data/dashboard.json").json();
const teamTimeseries = FileAttachment("./data/team-timeseries.json").json();
const playerHistory = FileAttachment("./data/player-history.json").json();
```

```tsx
import {Dashboard} from "./components/Dashboard.js";

display(<Dashboard data={dashboard} timeseries={teamTimeseries} playerHistory={playerHistory} />);
```
