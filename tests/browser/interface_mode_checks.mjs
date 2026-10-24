import assert from "node:assert/strict";

// Shared by both real-schema browser suites. The native button stays outside
// the DOM panel, so invoke the same callback LiteGraph invokes on the canvas.
export async function checkInterfaceModes(page) {
    const root = page.locator(".rs-nai-settings-panel");
    const before = await page.evaluate(() => ({ values: save(), inputs: node.inputs, order: node.originalOrder }));
    for (let cycle = 0; cycle < 3; cycle++) {
        await page.evaluate(() => node.widgets.find(w => w.name === "Panel / Classic widgets").callback());
        assert.equal(await root.isVisible(), false, "classic mode hides the panel");
        assert.equal(await page.evaluate(() => node.properties.rsNaiInterfaceMode), "classic");
        assert.deepEqual(await page.evaluate(() => save()), before.values);
        assert.deepEqual(await page.evaluate(() => node.inputs), before.inputs);
        assert.equal(await page.evaluate(() => node.widgets.some(w => w.rsNaiPanelVisible)), false);
        assert.ok(await page.evaluate(() => node.widgets.some(w => node.originalOrder.includes(w.name) && !w.hidden)), "native controls restored");
        assert.deepEqual(await page.evaluate(() => node.widgets.find(w => w.name.startsWith('rs_nai_') && w.element?.classList.contains('rs-nai-settings-panel')).computeSize()), [0, -4]);
        // Mode lives in serialized node properties, not in widget_values.
        await page.evaluate(() => {node.properties=JSON.parse(JSON.stringify(node.properties));node.onConfigure();node.onDrawForeground?.();});
        assert.equal(await root.isVisible(), false, "configure keeps classic mode");
        const name = await page.evaluate(() => node.comfyClass ?? 'NAIMultiCharacterDetailer');
        if (name === 'NAIMultiCharacterDetailer' || name === 'NAIDetectionCombineLoader') {
            const toggle = name === 'NAIMultiCharacterDetailer' ? 'show_advanced' : 'show_optional_models';
            const field = name === 'NAIMultiCharacterDetailer' ? 'dilation' : 'eye_bbox_model';
            const hidden = await page.evaluate(n => Boolean(getWidget(n).hidden), field);
            await page.evaluate(n => change(n, true), toggle);
            assert.equal(await page.evaluate(n => Boolean(getWidget(n).hidden), field), false, 'native expansion works');
            await page.evaluate(n => change(n, false), toggle);
            assert.equal(await page.evaluate(n => Boolean(getWidget(n).hidden), field), true, 'native collapse works');
            assert.equal(hidden, true);
        }
        await page.evaluate(() => node.widgets.find(w => w.name === "Panel / Classic widgets").callback());
        assert.equal(await root.isVisible(), true);
        assert.deepEqual(await page.evaluate(() => save()), before.values);
        assert.deepEqual(await page.evaluate(() => node.inputs), before.inputs);
        assert.deepEqual(await page.evaluate(() => node.widgets.filter(w => node.originalOrder.includes(w.name)).map(w => w.name)), before.order);
        assert.equal(await page.evaluate(() => node.widgets.filter(w => w.name === "Panel / Classic widgets").length), 1);
    }
    // Edits made through the original widget/callback appear in the panel.
    await page.evaluate(() => {
        node.rsNaiSettingsPanel.setMode('classic');
        window.modeProbe = node.widgets.find(w => node.originalOrder.includes(w.name) && !w.hidden && typeof w.value === 'number' && !node.inputs.some(i => i.name === w.name && i.link != null));
        window.modeProbeValue = modeProbe?.value;
        if (modeProbe) change(modeProbe.name, modeProbe.value + 1);
        node.rsNaiSettingsPanel.setMode('panel');
    });
    const probe = await page.evaluate(() => modeProbe && { name: modeProbe.name, value: modeProbe.value });
    if (probe) {
        for (const tab of await root.getByRole('tab').all()) {
            await tab.click();
            const input = root.locator(`[data-field="${probe.name}"] input[type=number]`);
            if (await input.count()) assert.equal(await input.inputValue(), String(probe.value));
        }
        await page.evaluate(() => change(modeProbe.name, modeProbeValue));
    }
    assert.deepEqual(await page.evaluate(() => save()), before.values);
}
