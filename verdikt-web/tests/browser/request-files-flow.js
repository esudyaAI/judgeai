async page => {
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('http://127.0.0.1:5178/app');
  await page.getByRole('textbox', {name:'Задача по делу'}).fill('First synthetic request.');
  await page.locator('input[type=file]').first().evaluate(input => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(['Synthetic document.'], 'old-request.txt', {type:'text/plain'}));
    input.files = transfer.files;
    input.dispatchEvent(new Event('change', {bubbles:true}));
  });
  await page.getByRole('button', {name:'Отправить',exact:true}).click();
  await page.locator('.result').waitFor();
  await page.getByRole('textbox', {name:'Задача по делу'}).fill('Follow-up without attachments.');
  await page.getByRole('button', {name:'Отправить',exact:true}).click();
  await page.locator('.thread-user .bubble').filter({hasText:'Follow-up without attachments.'}).waitFor();
  await page.locator('.result').waitFor();
  const requests = page.locator('.thread-user .bubble');
  if (await requests.count() !== 2) throw Error('Conversation history was lost');
  if (await requests.first().locator('.file-chip').count() !== 1) throw Error('Original attachment lost from history');
  if (await requests.last().locator('.file-chip').count()) throw Error('Old attachment duplicated as a new upload');
  return {history:'both turns retained',followupFiles:'old attachment remains in its original message'};
}
