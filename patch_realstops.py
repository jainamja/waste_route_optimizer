import io

with io.open('templates/live_tracking.html', 'r', encoding='utf-8') as f:
    text = f.read()

old_loop = """                stops.forEach(s => {
                    if (s.confirmation === 'CANCELLED') { tCanc++; cancList.push(s); }
                    else if (s.status === 'COMPLETED') { tComp++; compList.push(s); }
                    else if (s.status === 'SKIPPED') { tSkip++; skipList.push(s); }
                    else {
                        tLeft++;
                        if (leftList.length < 5) leftList.push(s);
                        if (s.confirmation === 'NOT_CONFIRMED') tNotConf++;
                    }
                });"""

new_loop = """                realStops.forEach(s => {
                    if (s.confirmation === 'CANCELLED') { tCanc++; cancList.push(s); }
                    else if (s.status === 'COMPLETED') { tComp++; compList.push(s); }
                    else if (s.status === 'SKIPPED') { tSkip++; skipList.push(s); }
                    else {
                        tLeft++;
                        if (leftList.length < 5) leftList.push(s);
                        if (s.confirmation === 'NOT_CONFIRMED') tNotConf++;
                    }
                });"""

text = text.replace(old_loop, new_loop)

with io.open('templates/live_tracking.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
