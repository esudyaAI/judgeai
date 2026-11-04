async page => {
  const results = [];
  for (const [width, height] of [[1440, 1000], [390, 844]]) {
    for (const fallback of [false, true]) {
      await page.unrouteAll({behavior: 'ignoreErrors'});
      let rest = 0, streams = 0;
      const messages = [{id: 1, role: 'assistant', content: 'Ответ через транспорт', status: 'completed', stage: null, result: null, attachments: []}];
      await page.route('http://127.0.0.1:5183/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/auth/me') return route.fulfill({json: {id:1, username:'synthetic', is_admin:false, csrf_token:'synthetic'}});
        if (path === '/api/chats') return route.fulfill({json:[{id:1, title:'SSE проверка', status:'ready', updated_at:'2026-11-04T00:00:00Z'}]});
        if (path === '/api/chats/1/messages/stream') {
          streams++;
          if (fallback) return route.fulfill({status:503, body:'Unavailable'});
          return route.fulfill({contentType:'text/event-stream', body:'event: messages\ndata: '+JSON.stringify(messages)+'\n\nevent: done\ndata: {}\n\n'});
        }
        if (path === '/api/chats/1/messages') { rest++; return route.fulfill({json:messages}); }
        return route.fulfill({json:{}});
      });
      await page.setViewportSize({width, height});
      await page.goto('http://127.0.0.1:5183/app/case/1/result');
      await page.getByText('Ответ через транспорт', {exact:true}).waitFor();
      if (!streams) throw Error('SSE was not requested');
      if (fallback ? !rest : rest !== 0) throw Error('Unexpected REST fallback: '+rest);
      if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error('Horizontal overflow');
      results.push({width, fallback, streams, rest});
    }
  }
  return results;
}
