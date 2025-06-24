var dagcomponentfuncs = window.dashAgGridComponentFunctions = window.dashAgGridComponentFunctions || {};

dagcomponentfuncs.DBC_Dual_Buttons = function (props) {
    const {setData, data} = props;

    function onClickOpen() {
        setData();
    }

    function onClickVisit() {
        // Open URL in new tab
        window.open(`https://mellitus.ens-lyon.fr/p3dx/viewer/${props.data.Name}`, '_blank');
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