import * as vscode from 'vscode';

export function registerTreeViews(context: vscode.ExtensionContext): void {
    const contextTreeProvider = new ContextTreeProvider();
    const hardwareTreeProvider = new HardwareTreeProvider();

    vscode.window.registerTreeDataProvider('ai-support.explorer', contextTreeProvider);
    vscode.window.registerTreeDataProvider('ai-support.hardware', hardwareTreeProvider);
}

class ContextTreeProvider implements vscode.TreeDataProvider<TreeItem> {
    getTreeItem(element: TreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: TreeItem): Thenable<TreeItem[]> {
        if (!element) {
            return Promise.resolve([
                new TreeItem('Peripherals', 'folder'),
                new TreeItem('Modules', 'folder'),
                new TreeItem('Drivers', 'folder'),
                new TreeItem('Configuration', 'folder')
            ]);
        }

        switch (element.label) {
            case 'Peripherals':
                return Promise.resolve([
                    new TreeItem('UART (USART1, USART2)', 'peripheral'),
                    new TreeItem('SPI (SPI1, SPI2)', 'peripheral'),
                    new TreeItem('GPIO', 'peripheral'),
                    new TreeItem('Timer', 'peripheral'),
                    new TreeItem('DMA', 'peripheral')
                ]);
            case 'Modules':
                return Promise.resolve([
                    new TreeItem('Communication', 'folder'),
                    new TreeItem('Motor Control', 'folder'),
                    new TreeItem('Sensors', 'folder'),
                    new TreeItem('Display', 'folder')
                ]);
            default:
                return Promise.resolve([]);
        }
    }
}

class HardwareTreeProvider implements vscode.TreeDataProvider<TreeItem> {
    getTreeItem(element: TreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: TreeItem): Thenable<TreeItem[]> {
        if (!element) {
            return Promise.resolve([
                new TreeItem('Clock Tree', 'clock'),
                new TreeItem('GPIO Map', 'gpio'),
                new TreeItem('Interrupts', 'interrupt'),
                new TreeItem('DMA Channels', 'dma')
            ]);
        }

        switch (element.label) {
            case 'Clock Tree':
                return Promise.resolve([
                    new TreeItem('HSI (16 MHz)', 'clock'),
                    new TreeItem('HSE (8 MHz)', 'clock'),
                    new TreeItem('PLL', 'clock'),
                    new TreeItem('APB1 (42 MHz)', 'clock'),
                    new TreeItem('APB2 (84 MHz)', 'clock')
                ]);
            case 'Interrupts':
                return Promise.resolve([
                    new TreeItem('EXTI0-15', 'interrupt'),
                    new TreeItem('USART1_IRQn', 'interrupt'),
                    new TreeItem('SPI1_IRQn', 'interrupt'),
                    new TreeItem('TIM2_IRQn', 'interrupt'),
                    new TreeItem('DMA1_Stream0', 'interrupt')
                ]);
            default:
                return Promise.resolve([]);
        }
    }
}

class TreeItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly iconType: string
    ) {
        super(label);
        this.iconPath = this.getIcon();
    }

    private getIcon(): vscode.ThemeIcon {
        const iconMap: Record<string, string> = {
            'folder': 'folder',
            'peripheral': 'circuit-board',
            'clock': 'clock',
            'interrupt': 'warning',
            'dma': 'arrow-both',
            'gpio': 'pin'
        };

        const iconName = iconMap[this.iconType] || 'file';
        return new vscode.ThemeIcon(iconName);
    }
}
