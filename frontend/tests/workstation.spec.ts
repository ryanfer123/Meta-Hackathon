import {test,expect} from '@playwright/test';

test('skip replay, inspect predicate and verify audit',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByRole('button',{name:'Play replay',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Seek to skipped',exact:true}).click();
 await expect(page.locator('.step.skipped')).toContainText('Cap tube 1');
 await expect(page.locator('.ledger')).toContainText('Later action label observed first.');
 await page.locator('.step').filter({hasText:'Cap tube 1'}).click();
 await expect(page.locator('.predicate-detail')).toContainText('touching');
 await page.getByRole('button',{name:'Open audit',exact:true}).first().click();
 await page.getByRole('button',{name:'Verify chain',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Chain matches this root');
 await page.getByLabel('Expected root hash').fill('0'.repeat(64));
 await page.getByRole('button',{name:'Verify chain',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('Verification failed');
 expect(errors).toEqual([]);
});

test('clean sample completes all steps and playback resets',async({page})=>{
 await page.goto('/');await page.getByLabel('Sample scenario').selectOption('clean');
 await expect(page.getByRole('button',{name:'Play replay',exact:true})).toBeVisible();
 await page.getByRole('slider',{name:'Replay position'}).focus();await page.keyboard.press('End');
 await expect(page.locator('.step.done')).toHaveCount(4);await expect(page.locator('.alert')).toHaveCount(0);
 await page.getByRole('button',{name:'Restart replay'}).click();
 await expect(page.getByRole('slider')).toHaveValue('0');
 await page.getByRole('button',{name:'Play replay',exact:true}).click();
 await expect(page.getByRole('button',{name:'Pause replay',exact:true})).toBeVisible();
 await expect.poll(async()=>Number(await page.getByRole('slider').inputValue())).toBeGreaterThan(0);
 await page.getByRole('button',{name:'Pause replay',exact:true}).click();
});

for(const [name,expected] of [['wrong-tube','wrong object'],['swapped-order','out of order'],['slow-action','dwell exceeded'],['occlusion','uncertain']]){
 test(`${name} shows its rule deviation`,async({page})=>{
  await page.goto('/');await page.getByLabel('Sample scenario').selectOption(name);
  await expect(page.getByRole('button',{name:'Play replay',exact:true})).toBeVisible();
  await page.getByRole('slider',{name:'Replay position'}).focus();await page.keyboard.press('End');
  await expect(page.locator('.ledger')).toContainText(expected,{ignoreCase:true});
 });
}

test('learn exposes pending evidence and mobile has no page overflow',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Upload a recording',exact:true}).click();
 await expect(page.getByRole('button',{name:'Compile protocol',exact:true})).toBeDisabled();
 await expect(page.locator('.validation-checks .pending')).toHaveCount(4);
 await page.locator('#narration').fill('[{"start":0,"end":2,"text":"Retained narration"}]');
 await page.getByRole('button',{name:'Supervise',exact:true}).click();
 await page.getByRole('button',{name:'Learn',exact:true}).click();
 await expect(page.locator('#narration')).toHaveValue('[{"start":0,"end":2,"text":"Retained narration"}]');
 await expect(page.getByText('Sample protocol · synthetic fixture · not learned from video.')).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);expect(overflow).toBeFalsy();
 await page.getByRole('button',{name:'Scope & provenance',exact:true}).click();
 await expect(page.getByRole('dialog')).toContainText('synthetic masks');
 await page.getByRole('button',{name:'Back to the workstation'}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('report is standalone and chain export downloads',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Open audit',exact:true}).first().click();
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Export chain',exact:true}).click();
 expect((await download).suggestedFilename()).toBe('sample-skipped-cap-chain.json');
 const url=await page.getByRole('link',{name:'HTML report'}).getAttribute('href');
 const response=await page.request.get(url!);expect(response.ok()).toBeTruthy();
 expect(await response.text()).toContain('Provenance: synthetic');
});
