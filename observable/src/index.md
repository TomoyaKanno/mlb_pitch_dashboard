---
title: MLB Pitch Workload
---

```js
const dashboard = FileAttachment("./data/dashboard.json").json();
// Sibling team-day increments for future timecourse charts; not rendered yet.
const teamTimeseries = FileAttachment("./data/team-timeseries.json").json();
```

```tsx
import {Dashboard} from "./components/Dashboard.js";

display(<Dashboard data={dashboard} />);
```
