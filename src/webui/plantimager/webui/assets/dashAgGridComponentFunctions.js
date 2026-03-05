var dagcomponentfuncs = window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};

dagcomponentfuncs.DBC_Dual_Buttons = function (props) {
    const {setData, data} = props;

    function onClickOpen() {
        setData();
    }

    function onClickVisit() {
        // Resolve the base URL: use the env variable if present, otherwise default
        const baseUrl = typeof P3DX_URL !== 'undefined' && P3DX_URL
            ? P3DX_URL
            : 'http://127.0.0.1:5050';

        // Open the viewer for the current row in a new tab
        window.open(`${baseUrl}/viewer/${props.data.Name}`, '_blank');
    }

    return React.createElement(
        'div',
        {
            style: {
                display: 'flex',
                gap: '5px'
            }
        },
        [
            React.createElement(
                window.dash_bootstrap_components.Button,
                {
                    onClick: onClickOpen,
                    color: props.color || 'primary',
                    key: 'open-button'
                },
                props.value || 'Open'
            ),
            React.createElement(
                window.dash_bootstrap_components.Button,
                {
                    onClick: onClickVisit,
                    color: 'secondary',
                    key: 'visit-button'
                },
                'P3DX'
            )
        ]
    );
};