const { test, expect } = require('@playwright/test')

test('knowledge workspace exposes wiki, review, agent, evidence and health views', async ({ page, request }) => {
  const source = await request.post('http://127.0.0.1:18765/api/v1/sources/ingest', {
    data: {
      title: 'Workspace evidence fixture',
      canonical_url: 'https://example.com/evidence',
      srt_content: '1\n00:00:01,000 --> 00:00:03,000\nTraceable evidence.\n',
      note_content: '# Workspace evidence fixture\n',
    },
  })
  expect(source.ok()).toBeTruthy()
  const { source_id: sourceId } = await source.json()

  await page.goto('/#/workspace/wiki')
  await expect(page.getByRole('tree')).toBeVisible()
  await expect(page.getByTestId('workspace-main')).toBeVisible()

  await page.goto(`/#/workspace/sources/${sourceId}?start=1000&end=3000`)
  await expect(page.getByRole('heading', { name: 'Workspace evidence fixture' })).toBeVisible()
  await expect(page.getByText('仅字幕证据')).toBeVisible()
  await expect(page.getByText('Traceable evidence.')).toBeVisible()

  await page.getByRole('link', { name: '变更审批' }).click()
  await expect(page.getByRole('heading', { name: '变更审批' })).toBeVisible()
  await page.getByRole('link', { name: 'Agent 会话' }).click()
  await expect(page.getByRole('heading', { name: 'Agent 会话' })).toBeVisible()
  await page.getByRole('link', { name: 'Wiki 健康' }).click()
  await expect(page.getByRole('heading', { name: 'Wiki 健康检查' })).toBeVisible()
})
