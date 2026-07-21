---
title: MLB Pitch Workload
---

```js
const dashboard = FileAttachment("./data/dashboard.json").json();
const teamTimeseries = FileAttachment("./data/team-timeseries.json").json();
```

```tsx
import {Dashboard} from "./components/Dashboard.js";

display(<Dashboard data={dashboard} timeseries={teamTimeseries} />);
```
