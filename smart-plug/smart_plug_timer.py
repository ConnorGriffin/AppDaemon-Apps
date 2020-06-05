import appdaemon.plugins.hass.hassapi as hass
import datetime


class SmartPlugTimer(hass.Hass):

    def initialize(self):
        for timer in self.args['timers']:
            self.run_minutely(
                callback=self.timer_eval_callback,
                start=datetime.time(0, 0, 0),
                timer=timer,
                constrain_input_boolean=timer['constrain_input_boolean']
            )

            self.listen_state(
                callback=self.time_input_changed_callback,
                entity=timer['start_time'],
                timer=timer,
                constrain_input_boolean=timer['constrain_input_boolean']
            )

            self.listen_state(
                callback=self.time_input_changed_callback,
                entity=timer['end_time'],
                timer=timer,
                constrain_input_boolean=timer['constrain_input_boolean']
            )

    def timer_eval_callback(self, kwargs):
        timer = kwargs.get('timer')
        switch_entity = timer.get('switch')
        switch_friendly = self.friendly_name(switch_entity)
        start_time = self.get_state(timer.get('start_time'))
        end_time = self.get_state(timer.get('end_time'))

        if self.now_is_between(start_time, end_time):
            if self.get_state(switch_entity) != 'on':
                self.turn_on(switch_entity)
                self.log('Turning on {}'.format(switch_friendly))
        else:
            if self.get_state(switch_entity) != 'off':
                self.turn_off(switch_entity)
                self.log('Turning off {}'.format(switch_friendly))

    def time_input_changed_callback(self, entity, attribute, old, new, kwargs):
        """ Runs when one of the time inputs changes, reevalulates the current timer based on the new values """
        self.run_in(
            callback=self.timer_eval_callback,
            delay=0,
            timer=kwargs.get('timer')
        )
