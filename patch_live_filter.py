import io
import re

with io.open('templates/live_dashboard.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Auto-select truck filter if provided in URL
old_load = """                      document.getElementById('conf-filter').value = 'all';
                      renderConfList();
                  });
          }"""

new_load = """                      document.getElementById('conf-filter').value = 'all';
                      renderConfList();
                      
                      let filterId = new URLSearchParams(window.location.search).get('truck_id');
                      if (filterId && document.getElementById('truck-filter')) {
                          let sel = document.getElementById('truck-filter');
                          // Only set if option exists
                          for(let i=0; i<sel.options.length; i++) {
                              if (sel.options[i].value == filterId) {
                                  sel.value = filterId;
                                  renderMap();
                                  break;
                              }
                          }
                      }
                  });
          }"""

text = text.replace(old_load, new_load)

with io.open('templates/live_dashboard.html', 'w', encoding='utf-8', newline='') as f:
    f.write(text)
print("Done")
